"""
TestPilot AI 应用入口

创建并配置 FastAPI 应用实例，组装所有模块。
采用应用工厂模式，便于测试时注入不同的依赖。
"""

from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from loguru import logger

from src import __app_name__, __version__
from src.api.routes import create_router
from src.api.websocket import ws_manager
from src.browser.automator import BrowserAutomator
from src.core.ai_client import AIClient
from src.core.config import get_config
from src.core.logger import setup_logger
from src.memory.store import MemoryStore
from src.sandbox.manager import SandboxManager
from src.auth.database import init_db as init_auth_db
from src.auth.routes import router as auth_router
from src.auth.team_routes import router as team_router
from src.community.routes import router as community_router
from src.billing.routes import router as billing_router
from src.admin.routes import router as admin_router


def create_app() -> FastAPI:
    """创建并配置 FastAPI 应用实例。

    Returns:
        FastAPI: 配置好的应用实例
    """
    config = get_config()

    # 初始化日志系统
    setup_logger(log_level=config.server.log_level, debug=config.debug)

    # 创建核心组件
    sandbox_manager = SandboxManager(config.sandbox)
    browser_automator = BrowserAutomator(config.browser)

    # v6.0：初始化用户系统数据库
    init_auth_db()

    # 记忆系统（SQLite 本地存储，零外部依赖）
    memory_store = MemoryStore()

    # AI 客户端（API Key 未配置时优雅降级，测试任务端点将返回503）
    ai_client: AIClient | None = None
    if config.ai.api_key:
        try:
            ai_client = AIClient(config.ai)
        except Exception as e:
            logger.warning("AI 客户端初始化失败（测试任务不可用）: {}", e)
    else:
        logger.warning("TP_AI_API_KEY 未配置，测试任务功能不可用")

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
        """应用生命周期管理：启动时初始化资源，关闭时清理。"""
        logger.info(
            "🚀 {} v{} 正在启动 | {}:{}",
            __app_name__,
            __version__,
            config.server.host,
            config.server.port,
        )
        yield
        # 关闭时清理所有资源
        logger.info("正在关闭服务，清理资源...")
        await browser_automator.close()
        sandbox_manager.close()
        memory_store.close()
        logger.info("{} 已安全关闭", __app_name__)

    app = FastAPI(
        title=__app_name__,
        description="AI驱动的自动化测试机器人 - 像人类一样操作UI、发现Bug、自动修复",
        version=__version__,
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # 注册路由
    router = create_router(sandbox_manager, browser_automator, ai_client, memory_store)
    app.include_router(router, prefix="/api/v1")
    app.include_router(auth_router, prefix="/api/v1")  # v6.0: 认证+项目+用量
    app.include_router(team_router, prefix="/api/v1")  # v6.1: 团队协作
    app.include_router(community_router, prefix="/api/v1")  # v13.0: 社区经验库
    app.include_router(billing_router, prefix="/api/v1")  # v13.0: 积分计费
    app.include_router(admin_router, prefix="/api/v1")  # v13.0-D: 管理后台

    # WebSocket 端点（IDE 插件实时通信）
    from fastapi import WebSocket, WebSocketDisconnect

    @app.websocket("/ws")
    async def websocket_endpoint(ws: WebSocket) -> None:
        await ws_manager.connect(ws)
        try:
            while True:
                # v2.0：接收并处理客户端消息（控制命令/心跳）
                raw = await ws.receive_text()
                await ws_manager.handle_message(ws, raw)
        except WebSocketDisconnect:
            ws_manager.disconnect(ws)

    # ── v10.1：被测应用预览服务器 ──────────────────────
    # 自动扫描工作区中含 testpilot.json 的目录，挂载为
    #   /preview/{dirname}/  →  对应目录的静态文件
    # 这样用户不需要手动启动 http-server，一键启动引擎即可测试

    project_root = Path(__file__).resolve().parent.parent
    _preview_dirs: dict[str, Path] = {}

    # 扫描第一层子目录中含蓝本的目录（支持 testpilot.json 或 testpilot/ 子目录）
    for child in project_root.iterdir():
        if not child.is_dir():
            continue
        has_bp = (child / "testpilot.json").exists()
        tp_dir = child / "testpilot"
        if not has_bp and tp_dir.is_dir():
            has_bp = any(tp_dir.glob("*.json"))
        if has_bp:
            _preview_dirs[child.name] = child

    if _preview_dirs:
        from fastapi.responses import FileResponse, HTMLResponse

        @app.get("/preview")
        async def list_preview_apps():
            """列出所有可预览的被测应用。"""
            items = [
                f'<li><a href="/preview/{name}/">{name}</a></li>'
                for name in sorted(_preview_dirs)
            ]
            html = (
                "<h2>TestPilot 被测应用预览</h2><ul>"
                + "".join(items) + "</ul>"
            )
            return HTMLResponse(html)

        @app.get("/preview/{app_name}")
        async def redirect_preview(app_name: str):
            """无斜杠时重定向到带斜杠版本。"""
            from fastapi.responses import RedirectResponse
            return RedirectResponse(url=f"/preview/{app_name}/", status_code=301)

        @app.get("/preview/{app_name}/{file_path:path}")
        async def serve_preview(app_name: str, file_path: str):
            """提供被测应用的静态文件服务。"""
            if app_name not in _preview_dirs:
                return HTMLResponse("应用不存在", status_code=404)
            base = _preview_dirs[app_name]
            target = (base / file_path) if file_path else (base / "index.html")
            # 安全检查：防止路径穿越
            try:
                target = target.resolve()
                if not str(target).startswith(str(base.resolve())):
                    return HTMLResponse("禁止访问", status_code=403)
            except (OSError, ValueError):
                return HTMLResponse("无效路径", status_code=400)
            if target.is_file():
                return FileResponse(target)
            # 默认返回 index.html
            index = base / "index.html"
            if index.is_file():
                return FileResponse(index)
            return HTMLResponse("文件不存在", status_code=404)

        for name in sorted(_preview_dirs):
            logger.info("预览服务已挂载: /preview/{}/", name)

    # v13.0: 社区门户 / v2.0: Web仪表盘 静态文件服务
    # 优先使用 web/dist（社区门户），回退到 desktop/dist（旧仪表盘）
    community_dist = Path(__file__).resolve().parent.parent / "web" / "dist"
    dashboard_dist = Path(__file__).resolve().parent.parent / "desktop" / "dist"
    spa_dist = community_dist if community_dist.is_dir() else dashboard_dist

    if spa_dist.is_dir():
        from fastapi.responses import FileResponse

        @app.get("/")
        async def serve_spa_index():
            """社区门户/仪表盘首页。"""
            return FileResponse(spa_dist / "index.html")

        @app.get("/{path:path}")
        async def serve_spa(path: str):
            """SPA回退：静态资源直接返回，其他路径返回index.html。"""
            file_path = spa_dist / path
            if file_path.is_file():
                return FileResponse(file_path)
            return FileResponse(spa_dist / "index.html")

        label = "社区门户" if spa_dist == community_dist else "Web仪表盘"
        logger.info("{}已启用 | 路径={}", label, spa_dist)
    else:
        logger.info("Web前端未构建（web/dist/ 和 desktop/dist/ 都不存在），跳过静态文件服务")

    return app


# uvicorn 需要的应用实例
app = create_app()
