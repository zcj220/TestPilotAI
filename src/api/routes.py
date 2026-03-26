"""
FastAPI 路由定义

提供 RESTful API 端点：
- /health: 健康检查
- /sandbox/*: 沙箱管理（创建/状态/执行命令/日志/销毁）
- /browser/*: 浏览器操作（启动/导航/点击/输入/截图/关闭）
"""

import json

from fastapi import APIRouter, HTTPException
from loguru import logger

from src.api.models import (
    BatchReportItem,
    BatchTestReportResponse,
    BlueprintListResponse,
    BlueprintSummary,
    BrowserResponse,
    ClickRequest,
    CommandResponse,
    CreateSandboxRequest,
    ExecCommandRequest,
    ExploreRequest,
    FillRequest,
    GenerateBlueprintRequest,
    GenerateBlueprintResponse,
    HealthResponse,
    NavigateRequest,
    RunBlueprintBatchRequest,
    RunBlueprintRequest,
    RunMobileBlueprintRequest,
    RunTestRequest,
    SandboxResponse,
    ScreenshotRequest,
    TestReportResponse,
)
from src.api.vnc import live_view
from src.api.websocket import ws_manager
from src.browser.automator import BrowserAutomator
from src.core.ai_client import AIClient
from src.core.exceptions import BrowserError, SandboxError
from src.memory.store import MemoryStore
from src.sandbox.manager import SandboxManager
from src.testing.blueprint import BlueprintParser
from src.testing.blueprint_runner import BlueprintRunner
from src.testing.controller import test_controller
from src.testing.cross_validator import CrossValidator
from src.testing.explorer import PageExplorer
from src.testing.process_runner import process_runner
from src.testing.orchestrator import TestOrchestrator


def _auto_preview_url(base_url: str, blueprint_path: str) -> str:
    """自动将蓝本的 base_url 转为引擎内置的 preview URL。

    如果 blueprint 所在目录是引擎工作区的子目录（含 index.html），
    就生成 /preview/{dirname}/ 形式的 URL，无需用户手动启动静态服务器。
    """
    import socket
    from pathlib import Path
    from urllib.parse import urlparse
    from src.core.config import get_config

    if not base_url or not blueprint_path:
        return base_url

    # 解析当前 base_url 的端口，检查是否可达
    parsed = urlparse(base_url)
    host = parsed.hostname or "localhost"
    port = parsed.port

    if port:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(0.5)
            if s.connect_ex((host, port)) == 0:
                s.close()
                return base_url  # 端口可达，不改
            s.close()
        except OSError:
            pass

    # 端口不可达 → 看蓝本所在目录是否在工作区中
    bp_path = Path(blueprint_path).resolve()
    app_dir = bp_path.parent
    project_root = Path(__file__).resolve().parent.parent.parent

    # 确保是工作区子目录且含 index.html
    try:
        app_dir.relative_to(project_root)
    except ValueError:
        return base_url

    if not (app_dir / "index.html").exists():
        return base_url

    cfg = get_config()
    engine_port = cfg.server.port
    preview_url = f"http://localhost:{engine_port}/preview/{app_dir.name}/"
    logger.info(
        "自动切换 base_url: {} → {}（原端口不可达）",
        base_url, preview_url,
    )
    return preview_url


def create_router(
    sandbox_manager: SandboxManager,
    browser_automator: BrowserAutomator,
    ai_client: AIClient | None = None,
    memory_store: MemoryStore | None = None,
) -> APIRouter:
    """创建 API 路由器。

    Args:
        sandbox_manager: 沙箱管理器实例
        browser_automator: 浏览器自动化引擎实例
        ai_client: AI 客户端实例（可选，测试任务需要）
        memory_store: 记忆存储实例（可选，测试历史需要）

    Returns:
        APIRouter: 配置好的路由器
    """
    router = APIRouter()

    # ── 健康检查 ──────────────────────────────────────

    @router.get("/health", response_model=HealthResponse, tags=["系统"])
    async def health_check() -> HealthResponse:
        """服务健康检查。"""
        from src import __version__
        return HealthResponse(
            status="healthy",
            version=__version__,
            sandbox_count=len(sandbox_manager.list_sandboxes()),
            browser_ready=browser_automator._page is not None,
        )

    @router.get("/preview/apps", tags=["系统"])
    async def list_preview_apps() -> list[dict]:
        """列出可预览的被测应用。

        返回项目中含 testpilot.json 的目录，及其对应的预览 URL。
        """
        from pathlib import Path
        from src.core.config import get_config
        cfg = get_config()
        port = cfg.server.port
        root = Path(__file__).resolve().parent.parent.parent
        apps = []
        for child in sorted(root.iterdir()):
            if not child.is_dir():
                continue
            bp_file = child / "testpilot.json"
            tp_dir = child / "testpilot"
            has_bp = bp_file.exists()
            if not has_bp and tp_dir.is_dir():
                has_bp = any(tp_dir.glob("*.json"))
            if has_bp:
                apps.append({
                    "name": child.name,
                    "path": str(child),
                    "blueprint_dir": str(tp_dir) if tp_dir.is_dir() else str(bp_file.parent),
                    "preview_url": f"http://localhost:{port}/preview/{child.name}/",
                })
        return apps

    # ── 沙箱管理 ──────────────────────────────────────

    @router.post("/sandbox/create", response_model=SandboxResponse, tags=["沙箱"])
    async def create_sandbox(req: CreateSandboxRequest) -> SandboxResponse:
        """创建并启动测试沙箱。"""
        try:
            sid = sandbox_manager.create(req.project_path, req.app_port)
            status = sandbox_manager.get_status(sid)
            return SandboxResponse(sandbox_id=sid, message="沙箱创建成功", status=status)
        except FileNotFoundError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except SandboxError as e:
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/sandbox/{sandbox_id}/status", response_model=SandboxResponse, tags=["沙箱"])
    async def get_sandbox_status(sandbox_id: str) -> SandboxResponse:
        """获取沙箱状态。"""
        try:
            status = sandbox_manager.get_status(sandbox_id)
            return SandboxResponse(sandbox_id=sandbox_id, message="查询成功", status=status)
        except SandboxError as e:
            raise HTTPException(status_code=404, detail=str(e))

    @router.post("/sandbox/{sandbox_id}/exec", response_model=CommandResponse, tags=["沙箱"])
    async def exec_in_sandbox(sandbox_id: str, req: ExecCommandRequest) -> CommandResponse:
        """在沙箱内执行命令。"""
        try:
            exit_code, output = sandbox_manager.exec_command(
                sandbox_id, req.command, req.workdir,
            )
            return CommandResponse(exit_code=exit_code, output=output)
        except SandboxError as e:
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/sandbox/{sandbox_id}/logs", tags=["沙箱"])
    async def get_sandbox_logs(sandbox_id: str, tail: int = 100) -> dict:
        """获取沙箱日志。"""
        try:
            logs = sandbox_manager.get_logs(sandbox_id, tail=tail)
            return {"sandbox_id": sandbox_id, "logs": logs}
        except SandboxError as e:
            raise HTTPException(status_code=404, detail=str(e))

    @router.delete("/sandbox/{sandbox_id}", response_model=SandboxResponse, tags=["沙箱"])
    async def destroy_sandbox(sandbox_id: str) -> SandboxResponse:
        """销毁沙箱。"""
        try:
            sandbox_manager.destroy(sandbox_id)
            return SandboxResponse(sandbox_id=sandbox_id, message="沙箱已销毁")
        except SandboxError as e:
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/sandbox", tags=["沙箱"])
    async def list_sandboxes() -> list[dict]:
        """列出所有活跃沙箱。"""
        return sandbox_manager.list_sandboxes()

    # ── 浏览器操作 ────────────────────────────────────

    @router.post("/browser/launch", response_model=BrowserResponse, tags=["浏览器"])
    async def launch_browser(cdp_url: str = "") -> BrowserResponse:
        """启动浏览器（本地或连接远程）。"""
        try:
            await browser_automator.launch(cdp_url=cdp_url or None)
            return BrowserResponse(success=True, message="浏览器已启动")
        except BrowserError as e:
            raise HTTPException(status_code=500, detail=str(e))

    @router.post("/browser/navigate", response_model=BrowserResponse, tags=["浏览器"])
    async def navigate(req: NavigateRequest) -> BrowserResponse:
        """导航到指定 URL。"""
        try:
            await browser_automator.navigate(req.url, req.wait_until)
            current_url = await browser_automator.get_current_url()
            title = await browser_automator.page.title()
            return BrowserResponse(
                success=True,
                message="导航成功",
                data={"url": current_url, "title": title},
            )
        except BrowserError as e:
            raise HTTPException(status_code=500, detail=str(e))

    @router.post("/browser/click", response_model=BrowserResponse, tags=["浏览器"])
    async def click(req: ClickRequest) -> BrowserResponse:
        """点击页面元素。"""
        try:
            await browser_automator.click(req.selector)
            return BrowserResponse(success=True, message=f"已点击: {req.selector}")
        except BrowserError as e:
            raise HTTPException(status_code=500, detail=str(e))

    @router.post("/browser/fill", response_model=BrowserResponse, tags=["浏览器"])
    async def fill(req: FillRequest) -> BrowserResponse:
        """在输入框中填入文本。"""
        try:
            await browser_automator.fill(req.selector, req.text)
            return BrowserResponse(success=True, message=f"已输入: {req.selector}")
        except BrowserError as e:
            raise HTTPException(status_code=500, detail=str(e))

    @router.post("/browser/screenshot", response_model=BrowserResponse, tags=["浏览器"])
    async def take_screenshot(req: ScreenshotRequest) -> BrowserResponse:
        """截取页面截图。"""
        try:
            filepath = await browser_automator.screenshot(req.name, req.full_page)
            return BrowserResponse(
                success=True,
                message="截图成功",
                data={"path": str(filepath)},
            )
        except BrowserError as e:
            raise HTTPException(status_code=500, detail=str(e))

    @router.post("/browser/close", response_model=BrowserResponse, tags=["浏览器"])
    async def close_browser() -> BrowserResponse:
        """关闭浏览器。"""
        await browser_automator.close()
        return BrowserResponse(success=True, message="浏览器已关闭")

    # ── 测试任务 ──────────────────────────────────────

    @router.post("/test/run", response_model=TestReportResponse, tags=["测试"])
    async def run_test(req: RunTestRequest) -> TestReportResponse:
        """启动 AI 自动化测试任务。

        完整流程：AI生成脚本 → 执行浏览器操作 → 截图分析 → Bug检测 → 生成报告
        """
        if ai_client is None:
            raise HTTPException(
                status_code=503,
                detail="AI 客户端未配置，请设置 TP_AI_API_KEY 环境变量",
            )

        # 确保浏览器健康可用（自动重置损坏的页面，无需重启引擎）
        try:
            await browser_automator.ensure_healthy()
        except BrowserError as e:
            raise HTTPException(status_code=500, detail=f"浏览器启动失败: {e}")

        orchestrator = TestOrchestrator(ai_client, browser_automator, memory_store)

        try:
            await ws_manager.send_log(f"开始测试: {req.url}")
            report = await orchestrator.run_test(
                url=req.url,
                description=req.description,
                focus=req.focus,
                reasoning_effort=req.reasoning_effort,
                auto_repair=req.auto_repair,
                project_path=req.project_path,
            )
            try:
                await ws_manager.send_test_done(report.pass_rate, len(report.bugs))
            except Exception as ws_err:
                logger.warning("WS推送test_done失败: {}", str(ws_err)[:100])

            # 构建响应
            repair_summary = None
            fixed_bug_count = None
            if report.repair_report is not None:
                repair_summary = report.repair_report.summary
                fixed_bug_count = report.repair_report.fixed_bugs

            return TestReportResponse(
                test_name=report.test_name,
                url=report.url,
                total_steps=report.total_steps,
                passed_steps=report.passed_steps,
                failed_steps=report.failed_steps,
                bug_count=len(report.bugs),
                pass_rate=report.pass_rate,
                duration_seconds=report.duration_seconds,
                report_markdown=report.report_markdown,
                repair_summary=repair_summary,
                fixed_bug_count=fixed_bug_count,
            )
        except Exception as e:
            logger.error("测试任务执行失败: {}", e)
            raise HTTPException(status_code=500, detail=f"测试执行失败: {e}")

    @router.post("/test/blueprint", response_model=TestReportResponse, tags=["测试"])
    async def run_blueprint_test(req: RunBlueprintRequest) -> TestReportResponse:
        """蓝本模式测试：按 testpilot.json 精确执行。

        蓝本由编程AI生成，包含精确的CSS选择器和预期结果，
        不需要测试AI猜测页面结构。
        """
        # 解析蓝本
        try:
            blueprint = BlueprintParser.parse_file(req.blueprint_path)
        except FileNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

        # 验证蓝本
        issues = BlueprintParser.validate(blueprint)
        if issues:
            raise HTTPException(
                status_code=400,
                detail=f"蓝本验证失败: {'; '.join(issues)}",
            )

        # 覆盖 base_url
        if req.base_url:
            blueprint.base_url = req.base_url

        # Android/iOS 蓝本 → 握手检测 + 自动创建 session 并路由到 MobileBlueprintRunner
        if blueprint.platform in ("android", "ios"):
            from src.controller.android import AndroidController, MobileConfig
            from src.testing.mobile_blueprint_runner import MobileBlueprintRunner

            if blueprint.platform == "ios":
                config = MobileConfig(
                    platform_name="iOS",
                    automation_name="XCUITest",
                    bundle_id=blueprint.bundle_id or "",
                    udid=blueprint.udid or "",
                )
            else:
                config = MobileConfig(
                    app_package=blueprint.app_package or "",
                    app_activity=blueprint.app_activity or "",
                )
            android_ctrl = AndroidController(config)

            # 握手：设备检测 → 自动启动 Appium → 创建 Session
            device_check = await android_ctrl.check_device()
            if not device_check["ok"]:
                raise HTTPException(status_code=400, detail=f"设备连接失败: {device_check['message']}")
            appium_result = await android_ctrl.ensure_appium_server(timeout=30)
            if not appium_result["ok"]:
                raise HTTPException(status_code=500, detail=f"Appium启动失败: {appium_result['message']}")

            try:
                await android_ctrl.launch()
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Appium Session创建失败: {e}")

            async def _on_step_m(step: int, status: str, desc: str) -> None:
                if status == "start":
                    await ws_manager.send_step_start(step, desc)
                else:
                    await ws_manager.send_step_done(step, status, desc)

            runner = MobileBlueprintRunner(
                android_ctrl, ai_client, on_step=_on_step_m,
                test_controller=test_controller,
            )

            try:
                await ws_manager.send_log(f"手机蓝本测试开始: {blueprint.app_name}")
                await ws_manager.send_test_started()  # 通知插件显示控制按钮
                report = await runner.run(blueprint)
                from src.api.models import StepDetail, BugDetail
                stopped = test_controller.was_stopped
                if stopped:
                    test_controller.reset()
                pass_rate = report.passed_steps / report.total_steps * 100 if report.total_steps > 0 else 0
                response = TestReportResponse(
                    test_name=report.test_name,
                    url=report.url,
                    total_steps=report.total_steps,
                    passed_steps=report.passed_steps,
                    failed_steps=report.failed_steps,
                    bug_count=len(report.bugs),
                    pass_rate=pass_rate,
                    duration_seconds=report.duration_seconds,
                    report_markdown=report.report_markdown,
                    stopped=stopped,
                    steps=[
                        StepDetail(
                            step=r.step,
                            action=r.action.value if hasattr(r.action, 'value') else str(r.action),
                            description=r.description,
                            status=r.status.value if hasattr(r.status, 'value') else str(r.status),
                            duration_seconds=r.duration_seconds,
                            error_message=r.error_message,
                            screenshot_path=r.screenshot_path,
                        )
                        for r in report.step_results
                    ],
                    bugs=[
                        BugDetail(
                            severity=b.severity.value if hasattr(b.severity, 'value') else str(b.severity),
                            title=b.title,
                            description=b.description,
                            category=b.category,
                            location=b.location,
                            step_number=b.step_number,
                            screenshot_path=b.screenshot_path,
                        )
                        for b in report.bugs
                    ],
                )
                try:
                    report_dict = response.model_dump()
                except AttributeError:
                    report_dict = response.dict()
                try:
                    await ws_manager.send_test_done(pass_rate, len(report.bugs), full_report=report_dict)
                except Exception as ws_err:
                    logger.warning("WS推送test_done失败: {}", str(ws_err)[:100])
                return response
            except Exception as e:
                logger.error("手机蓝本测试执行失败: {}", e)
                raise HTTPException(status_code=500, detail=f"手机蓝本测试执行失败: {e}")
            finally:
                try:
                    await android_ctrl.close()
                except Exception:
                    pass

        # v10.1：自动推断 preview URL
        # 如果蓝本在引擎工作区内（含 testpilot.json 的目录），
        # 且 base_url 指向的外部端口不可达，自动切换到 /preview/{dir}/
        blueprint.base_url = _auto_preview_url(
            blueprint.base_url, req.blueprint_path,
        )

        # v14.0-D：积分校验（仅云端登录模式，游客直接跳过）
        _credit_ctx: dict = {}  # 存储校验通过的积分信息，供测试完成后扣减
        if req.cloud_token:
            try:
                from src.auth.database import SessionLocal
                from src.auth import service as _auth_svc
                _payload = _auth_svc.decode_token(req.cloud_token)
                if _payload and "sub" in _payload:
                    _cloud_uid = int(_payload["sub"])
                    _required = _auth_svc.calc_blueprint_credits(blueprint.total_steps)
                    _db = SessionLocal()
                    try:
                        _chk = _auth_svc.check_credits(_db, _cloud_uid, _required)
                    finally:
                        _db.close()
                    if not _chk["ok"]:
                        raise HTTPException(
                            status_code=402,
                            detail=(
                                f"credits_insufficient"
                                f"|balance={_chk['balance']}"
                                f"|required={_required}"
                                f"|plan={_chk['plan']}"
                            ),
                        )
                    _credit_ctx = {"user_id": _cloud_uid, "required": _required, "app": blueprint.app_name}
                    logger.info("积分校验通过 | user_id={} required={} balance={}", _cloud_uid, _required, _chk['balance'])
            except HTTPException:
                raise
            except Exception as _ce:
                logger.warning("积分校验失败（允许继续，游客模式）: {}", _ce)

        # 确保浏览器健康可用（自动重置损坏的页面，无需重启引擎）
        try:
            await browser_automator.ensure_healthy()
        except BrowserError as e:
            raise HTTPException(status_code=500, detail=f"浏览器启动失败: {e}")

        # 执行蓝本测试（v2.0：注入控制器 + 截图推送 + 步骤通知）
        async def _on_screenshot(step: int, img_b64: str) -> None:
            await ws_manager.send_screenshot(step, img_b64)

        async def _on_step(step: int, status: str, desc: str) -> None:
            if status == "start":
                await ws_manager.send_step_start(step, desc)
            else:
                await ws_manager.send_step_done(step, status, desc)

        runner = BlueprintRunner(
            browser_automator, ai_client,
            controller=test_controller,
            on_screenshot=_on_screenshot,
            on_step=_on_step,
            step_interval_ms=req.step_interval_ms,
        )

        # 使用 StreamingResponse + 心跳保活，防止 HTTP 连接在长测试中断开
        # 每 20 秒发送一个空格作为心跳，测试完成后发送完整 JSON 结果
        import asyncio as _asyncio
        from fastapi.responses import StreamingResponse as _StreamingResponse

        result_holder: dict = {}

        async def _run_test():
            try:
                await ws_manager.send_log(f"蓝本测试开始: {blueprint.app_name}")
                report = await runner.run(blueprint)

                if memory_store and report.bugs:
                    try:
                        from src.memory.compressor import MemoryCompressor
                        compressor = MemoryCompressor(memory_store)
                        compressor.extract_from_report(report)
                    except Exception as mem_err:
                        logger.warning("蓝本测试记忆提取失败: {}", mem_err)

                from src.api.models import StepDetail, BugDetail
                stopped = test_controller.was_stopped
                if stopped:
                    test_controller.reset()
                pass_rate = report.passed_steps / report.total_steps * 100 if report.total_steps > 0 else 0
                response = TestReportResponse(
                    test_name=report.test_name,
                    url=report.url,
                    total_steps=report.total_steps,
                    passed_steps=report.passed_steps,
                    failed_steps=report.failed_steps,
                    bug_count=len(report.bugs),
                    pass_rate=pass_rate,
                    duration_seconds=report.duration_seconds,
                    report_markdown=report.report_markdown,
                    stopped=stopped,
                    steps=[
                        StepDetail(
                            step=r.step,
                            action=r.action.value if hasattr(r.action, 'value') else str(r.action),
                            description=r.description,
                            status=r.status.value if hasattr(r.status, 'value') else str(r.status),
                            duration_seconds=r.duration_seconds,
                            error_message=r.error_message,
                            screenshot_path=r.screenshot_path,
                        )
                        for r in report.step_results
                    ],
                    bugs=[
                        BugDetail(
                            severity=b.severity.value if hasattr(b.severity, 'value') else str(b.severity),
                            title=b.title,
                            description=b.description,
                            category=b.category,
                            location=b.location,
                            step_number=b.step_number,
                            screenshot_path=b.screenshot_path,
                        )
                        for b in report.bugs
                    ],
                )
                try:
                    report_dict = response.model_dump()
                except AttributeError:
                    report_dict = response.dict()
                try:
                    await ws_manager.send_test_done(pass_rate, len(report.bugs), full_report=report_dict)
                except Exception as ws_err:
                    logger.warning("WS推送test_done失败（不影响结果）: {}", str(ws_err)[:100])
                result_holder["data"] = report_dict

                # v14.0-D：测试完成后扣减积分
                if _credit_ctx:
                    try:
                        from src.auth.database import SessionLocal
                        from src.auth import service as _auth_svc2
                        _db2 = SessionLocal()
                        try:
                            _auth_svc2.deduct_credits(
                                _db2,
                                _credit_ctx["user_id"],
                                _credit_ctx["required"],
                                "blueprint_test",
                                _credit_ctx["app"],
                            )
                        finally:
                            _db2.close()
                    except Exception as _de:
                        logger.warning("积分扣减失败（不影响测试结果）: {}", _de)

            except Exception as e:
                logger.error("蓝本测试执行失败: {}", e)
                result_holder["error"] = str(e)

        async def _stream_with_heartbeat():
            task = _asyncio.create_task(_run_test())
            while not task.done():
                await _asyncio.sleep(20)
                if not task.done():
                    yield b" "  # 心跳空格，保持HTTP连接活跃
            await task  # 确保异常被传播
            if "error" in result_holder:
                import json as _json
                yield _json.dumps({"detail": result_holder["error"]}).encode("utf-8")
            else:
                import json as _json
                yield _json.dumps(result_holder.get("data", {})).encode("utf-8")

        return _StreamingResponse(
            _stream_with_heartbeat(),
            media_type="application/json",
        )

    @router.post("/test/mobile-blueprint", response_model=TestReportResponse, tags=["测试"])
    async def run_mobile_blueprint_test(req: RunMobileBlueprintRequest) -> TestReportResponse:
        """手机蓝本测试：在真实 Android 设备上按蓝本执行。

        如果 mobile_session_id 为空，自动检测设备并创建 Appium Session。
        蓝本中的 app_package/app_activity 会在 runner.run() 中用于重建
        带 appPackage 的完整 Session，确保 Appium 正确 instrument 被测 APP。
        """
        from src.testing.blueprint import BlueprintParser
        from src.testing.mobile_blueprint_runner import MobileBlueprintRunner
        from src.controller.android import AndroidController, MobileConfig

        # 解析蓝本（先解析，需要读取 app_package 等信息）
        try:
            blueprint = BlueprintParser.parse_file(req.blueprint_path)
        except FileNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        if req.base_url:
            blueprint.base_url = req.base_url

        # 获取或自动创建 Session
        auto_created_session = False
        if req.mobile_session_id and req.mobile_session_id in _mobile_sessions:
            android_ctrl = _mobile_sessions[req.mobile_session_id]
        else:
            # ── 握手检测：在 launch 之前先确认环境就绪 ──
            if blueprint.platform == "ios":
                config = MobileConfig(
                    platform_name="iOS",
                    automation_name="XCUITest",
                    bundle_id=blueprint.bundle_id or "",
                    udid=blueprint.udid or "",
                )
            else:
                config = MobileConfig(
                    device_name="",  # 自动检测
                    app_package=blueprint.app_package or "",
                    app_activity=blueprint.app_activity or "",
                )
            android_ctrl = AndroidController(config)

            # 第1步：检测设备连接
            device_check = await android_ctrl.check_device()
            if not device_check["ok"]:
                await ws_manager.send_log(f"❌ {device_check['message']}")
                raise HTTPException(
                    status_code=400,
                    detail=f"设备连接失败: {device_check['message']}",
                )
            await ws_manager.send_log(f"✅ {device_check['message']}")

            # 第2步：确保 Appium Server 运行（未启动则自动启动）
            await ws_manager.send_log("🔄 正在检测 Appium Server...")
            appium_result = await android_ctrl.ensure_appium_server(timeout=30)
            if not appium_result["ok"]:
                await ws_manager.send_log(f"❌ {appium_result['message']}")
                raise HTTPException(
                    status_code=500,
                    detail=f"Appium启动失败: {appium_result['message']}",
                )
            await ws_manager.send_log(f"✅ {appium_result['message']}")

            # 第3步：创建 Appium Session
            logger.info("握手成功，创建 Appium Session...")
            await ws_manager.send_log("🔄 正在创建 Appium Session...")
            try:
                await android_ctrl.launch()
                auto_created_session = True
                session_id = f"mobile_auto_{len(_mobile_sessions) + 1}"
                _mobile_sessions[session_id] = android_ctrl
                logger.info("自动创建 Session 成功 | ID={}", session_id)
                await ws_manager.send_log("✅ Appium Session 创建成功")

                # 蓝本权限批量授予
                if blueprint.permissions and blueprint.app_package:
                    await android_ctrl.grant_permissions(
                        blueprint.app_package, blueprint.permissions
                    )
            except Exception as e:
                logger.error("自动创建 Appium Session 失败: {}", e)
                raise HTTPException(
                    status_code=500,
                    detail=f"Appium Session 创建失败: {e}。设备和Appium均已就绪，但Session创建出错。",
                )

        async def _on_step(step: int, status: str, desc: str) -> None:
            if status == "start":
                await ws_manager.send_step_start(step, desc)
            else:
                await ws_manager.send_step_done(step, status, desc)

        runner = MobileBlueprintRunner(
            android_ctrl, ai_client, on_step=_on_step,
            test_controller=test_controller,
        )

        try:
            await ws_manager.send_log(f"手机蓝本测试开始: {blueprint.app_name}")
            await ws_manager.send_test_started()  # 通知插件显示控制按钮
            report = await runner.run(blueprint)
            from src.api.models import StepDetail, BugDetail
            stopped = test_controller.was_stopped
            if stopped:
                test_controller.reset()
            pass_rate = report.passed_steps / report.total_steps * 100 if report.total_steps > 0 else 0
            response = TestReportResponse(
                test_name=report.test_name,
                url=report.url,
                total_steps=report.total_steps,
                passed_steps=report.passed_steps,
                failed_steps=report.failed_steps,
                bug_count=len(report.bugs),
                pass_rate=pass_rate,
                duration_seconds=report.duration_seconds,
                report_markdown=report.report_markdown,
                stopped=stopped,
                steps=[
                    StepDetail(
                        step=r.step,
                        action=r.action.value if hasattr(r.action, 'value') else str(r.action),
                        description=r.description,
                        status=r.status.value if hasattr(r.status, 'value') else str(r.status),
                        duration_seconds=r.duration_seconds,
                        error_message=r.error_message,
                        screenshot_path=r.screenshot_path,
                    )
                    for r in report.step_results
                ],
                bugs=[
                    BugDetail(
                        severity=b.severity.value if hasattr(b.severity, 'value') else str(b.severity),
                        title=b.title,
                        description=b.description,
                        category=b.category,
                        location=b.location,
                        step_number=b.step_number,
                        screenshot_path=b.screenshot_path,
                    )
                    for b in report.bugs
                ],
            )
            # 通过WebSocket推送完整报告（含bugs+steps），插件侧边栏才能渲染Bug详情
            # WS推送失败不能影响HTTP返回（否则客户端拿不到bug详情）
            try:
                report_dict = response.model_dump()
            except AttributeError:
                report_dict = response.dict()
            try:
                await ws_manager.send_test_done(pass_rate, len(report.bugs), full_report=report_dict)
            except Exception as ws_err:
                logger.warning("WS推送test_done失败（不影响HTTP返回）: {}", str(ws_err)[:100])
            return response
        except Exception as e:
            logger.error("手机蓝本测试执行失败: {}", e)
            raise HTTPException(status_code=500, detail=f"手机蓝本测试执行失败: {e}")

    # ── 小程序蓝本测试（v10.2）───────────────────────────

    @router.post("/test/miniprogram-blueprint", response_model=TestReportResponse, tags=["测试"])
    async def run_miniprogram_blueprint_test(req: dict) -> TestReportResponse:
        """小程序蓝本测试：直接调用Node.js执行器（参照run_blind_test.js）。

        不使用桥接服务器！Python把蓝本步骤写成JSON，Node.js一次性执行完返回结果。
        需要：微信开发者工具已安装、已开启服务端口。
        """
        from pathlib import Path
        from src.testing.blueprint import BlueprintParser
        import subprocess as sp
        import tempfile
        import time
        import asyncio

        blueprint_path = req.get("blueprint_path", "")
        project_path = req.get("project_path", "")
        base_url_override = req.get("base_url", "")

        bp_file = Path(blueprint_path)
        if not bp_file.exists():
            raise HTTPException(status_code=400, detail=f"蓝本文件不存在: {blueprint_path}")

        try:
            blueprint = BlueprintParser.parse_file(str(bp_file))
            base_url = base_url_override or blueprint.base_url

            if not project_path and base_url.startswith("miniprogram://"):
                project_path = base_url.replace("miniprogram://", "")
            if not project_path:
                project_path = str(bp_file.parent)

            # 收集蓝本中所有步骤
            all_steps = []
            for page in blueprint.pages:
                for scenario in page.scenarios:
                    for step in scenario.steps:
                        all_steps.append({
                            "action": step.action,
                            "target": step.target or "",
                            "value": step.value or "",
                            "expected": step.expected or "",
                            "description": step.description or step.action,
                        })

            if not all_steps:
                raise HTTPException(status_code=400, detail="蓝本中没有可执行步骤（pages.scenarios.steps为空）")

            logger.info("小程序蓝本测试 | 项目:{} | 步骤数:{}", project_path, len(all_steps))

            # 写入临时JSON文件
            runner_input = {
                "project_path": project_path,
                "ws_port": 9420,
                "steps": all_steps,
            }
            tmp_file = Path(tempfile.mktemp(suffix=".json", prefix="mp_steps_"))
            tmp_file.write_text(json.dumps(runner_input, ensure_ascii=False), encoding="utf-8")

            # 调用Node.js执行器（跟run_blind_test.js一样的逻辑）
            runner_script = Path(__file__).parent.parent / "controller" / "miniprogram_runner.js"
            if not runner_script.exists():
                raise RuntimeError(f"执行器脚本不存在: {runner_script}")

            logger.info("启动Node.js执行器: {}", runner_script.name)
            start = time.time()

            # 用Popen实时读取stderr进度并推送WebSocket
            await ws_manager.send_log(f"小程序蓝本测试开始: {blueprint.app_name} | {len(all_steps)}步")
            proc = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: sp.Popen(
                    ["node", str(runner_script), str(tmp_file)],
                    stdout=sp.PIPE, stderr=sp.PIPE,
                    encoding="utf-8", errors="replace",
                )
            )

            # 同时读stdout和stderr（避免管道缓冲区满导致死锁）
            import threading
            _stderr_buf = []
            _stdout_chunks = []
            _stderr_done = threading.Event()
            _stdout_done = threading.Event()
            loop = asyncio.get_event_loop()

            def _stream_stderr():
                for line in proc.stderr:
                    _stderr_buf.append(line.rstrip())
                _stderr_done.set()

            def _stream_stdout():
                _stdout_chunks.append(proc.stdout.read())
                _stdout_done.set()

            threading.Thread(target=_stream_stderr, daemon=True).start()
            threading.Thread(target=_stream_stdout, daemon=True).start()

            _last_pushed = 0
            while not _stderr_done.is_set() or _last_pushed < len(_stderr_buf):
                await asyncio.sleep(0.3)
                while _last_pushed < len(_stderr_buf):
                    line = _stderr_buf[_last_pushed]
                    _last_pushed += 1
                    if line.startswith("[PROGRESS]"):
                        parts = line[len("[PROGRESS]"):].strip()
                        await ws_manager.send_log(f"🔄 {parts}")
                    elif line.startswith("[STEP]"):
                        parts = line[len("[STEP]"):].strip()
                        await ws_manager.send_log(parts)

            # 等stdout线程和进程结束
            _stdout_done.wait(timeout=30)
            await loop.run_in_executor(None, proc.wait)
            stdout_data = "".join(_stdout_chunks)

            # 清理临时文件
            try:
                tmp_file.unlink()
            except Exception:
                pass

            duration = time.time() - start
            logger.info("Node.js执行器完成 | 耗时:{:.1f}秒 | rc:{}", duration, proc.returncode)

            # 解析结果
            stdout = stdout_data or ""
            stderr = "\n".join(_stderr_buf)

            await ws_manager.send_log(f"小程序蓝本测试完成 | 耗时:{duration:.1f}秒")

            # 从stdout找JSON（最后一行）
            result_data = None
            for line in reversed(stdout.strip().split("\n")):
                line = line.strip()
                if line.startswith("{"):
                    try:
                        result_data = json.loads(line)
                        break
                    except json.JSONDecodeError:
                        continue

            if not result_data:
                logger.error("执行器无JSON输出:\nstdout:{}\nstderr:{}", stdout[-300:], stderr[-300:])
                hint = ""
                rc = proc.returncode
                if rc and rc != 0:
                    hint = f"执行器异常退出(rc={rc})。可能原因：小程序代码修改后未重新编译，或模拟器状态异常。请在微信开发者工具中点击'编译'后重试。"
                else:
                    hint = f"执行器无有效输出。stderr: {stderr[-200:]}"
                raise RuntimeError(hint)

            if not result_data.get("success"):
                raise RuntimeError(f"执行器失败: {result_data.get('error', '未知错误')}")

            # 转换为TestReport
            from src.testing.models import StepResult, TestReport, BugReport, ActionType, StepStatus, BugSeverity
            from datetime import datetime, timezone, timedelta

            def _to_action(s: str) -> ActionType:
                try:
                    return ActionType(s)
                except ValueError:
                    return ActionType.SCREENSHOT

            steps_results = []
            bugs = []
            for r in result_data.get("results", []):
                status = StepStatus.PASSED if r.get("status") == "passed" else StepStatus.FAILED
                sr = StepResult(
                    step=r.get("step", 0),
                    action=_to_action(r.get("action", "screenshot")),
                    status=status,
                    description=r.get("description", ""),
                    duration_seconds=r.get("duration", 0),
                    error_message=r.get("error", ""),
                )
                steps_results.append(sr)
                if status == StepStatus.FAILED:
                    bugs.append(BugReport(
                        severity=BugSeverity.MEDIUM,
                        title=f"步骤{r.get('step')}失败: {r.get('action')}",
                        description=r.get("error", ""),
                        step_number=r.get("step"),
                    ))

            total = len(steps_results)
            passed = result_data.get("passed", 0)
            failed = result_data.get("failed", 0)

            end_time = datetime.now(timezone.utc)
            start_time = end_time - timedelta(seconds=duration)

            report = TestReport(
                test_name=f"小程序蓝本测试-{blueprint.app_name}",
                url=base_url,
                start_time=start_time,
                end_time=end_time,
                total_steps=total,
                passed_steps=passed,
                failed_steps=failed,
                step_results=steps_results,
                bugs=bugs,
            )

            pass_rate = passed / total * 100 if total > 0 else 0

            from src.api.models import StepDetail, BugDetail
            response = TestReportResponse(
                test_name=report.test_name,
                url=report.url,
                total_steps=total,
                passed_steps=passed,
                failed_steps=failed,
                bug_count=len(bugs),
                pass_rate=pass_rate,
                duration_seconds=report.duration_seconds,
                report_markdown=report.report_markdown,
                steps=[
                    StepDetail(
                        step=r.step,
                        action=r.action.value if hasattr(r.action, 'value') else str(r.action),
                        description=r.description,
                        status=r.status.value if hasattr(r.status, 'value') else str(r.status),
                        duration_seconds=r.duration_seconds,
                        error_message=r.error_message,
                        screenshot_path=r.screenshot_path,
                    )
                    for r in steps_results
                ],
                bugs=[
                    BugDetail(
                        severity=b.severity.value if hasattr(b.severity, 'value') else str(b.severity),
                        title=b.title,
                        description=b.description,
                        step_number=b.step_number,
                    )
                    for b in bugs
                ],
            )
            try:
                report_dict = response.model_dump()
            except AttributeError:
                report_dict = response.dict()
            try:
                await ws_manager.send_test_done(pass_rate, len(bugs), full_report=report_dict)
            except Exception as ws_err:
                logger.warning("WS推送test_done失败: {}", str(ws_err)[:100])
            return response
        except HTTPException:
            raise
        except Exception as e:
            logger.error("小程序蓝本测试执行失败: {}", e)
            raise HTTPException(status_code=500, detail=f"小程序蓝本测试执行失败: {e}")

    # ── 桌面应用蓝本测试（v10.2）───────────────────────────

    @router.post("/test/desktop-blueprint", response_model=TestReportResponse, tags=["测试"])
    async def run_desktop_blueprint_test(req: dict) -> TestReportResponse:
        """桌面应用蓝本测试：UI Automation + AI视觉双保险。"""
        from pathlib import Path
        from src.testing.blueprint import BlueprintParser
        from src.controller.desktop import DesktopController
        from src.controller.window_manager import DesktopConfig
        from src.testing.desktop_blueprint_runner import DesktopBlueprintRunner

        blueprint_path = req.get("blueprint_path", "")
        base_url_override = req.get("base_url", "")

        bp_file = Path(blueprint_path)
        if not bp_file.exists():
            raise HTTPException(status_code=400, detail=f"蓝本文件不存在: {blueprint_path}")

        try:
            blueprint = BlueprintParser.parse_file(str(bp_file))
            if base_url_override:
                blueprint.base_url = base_url_override

            # 从蓝本JSON读取原始字段（BlueprintParser可能不解析这些），API参数可覆盖
            import json
            raw_bp = json.loads(bp_file.read_text(encoding="utf-8"))
            window_title = req.get("window_title", "") or raw_bp.get("window_title", "") or blueprint.app_name
            # app_exe 是桌面专用字段；start_command 是通用字段，桌面模式下作为 fallback
            app_exe = (req.get("app_exe", "") or raw_bp.get("app_exe", "")
                       or raw_bp.get("start_command", ""))
            bp_dir = bp_file.parent  # 蓝本所在目录，用于相对路径执行
            # 如果蓝本在 testpilot/ 子目录下，工作目录应为其父目录（项目根目录）
            if bp_dir.name == "testpilot":
                bp_dir = bp_dir.parent
            # start_cwd 优先作为工作目录（对 npm run electron:dev 等复杂命令至关重要）
            start_cwd = raw_bp.get("start_cwd", "") or req.get("start_cwd", "")
            if start_cwd:
                bp_dir = Path(start_cwd)

            # 自动启动/重启被测应用（确保干净状态）
            if app_exe:
                import subprocess, time, ctypes
                user32 = ctypes.windll.user32
                WM_CLOSE = 0x0010
                hwnd = user32.FindWindowW(None, window_title)
                if hwnd:
                    user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
                    logger.info("已关闭旧窗口: {} (hwnd={})", window_title, hwnd)
                    time.sleep(2)
                    # 等窗口真正关闭
                    for _ in range(10):
                        if not user32.FindWindowW(None, window_title):
                            break
                        time.sleep(0.3)
                # 如果命令以python开头，优先使用项目虚拟环境的python
                launch_cmd = app_exe
                if launch_cmd.startswith("python "):
                    venv_python = bp_dir.parent / ".venv" / "Scripts" / "python.exe"
                    if not venv_python.exists():
                        venv_python = bp_dir / ".venv" / "Scripts" / "python.exe"
                    if venv_python.exists():
                        launch_cmd = f'"{venv_python}" {launch_cmd[7:]}'
                subprocess.Popen(launch_cmd, shell=True, cwd=str(bp_dir))
                # 等待窗口出现，最多30秒（npm run electron:dev 需要先启动vite，耗时较长）
                for _wait in range(60):
                    time.sleep(0.5)
                    if user32.FindWindowW(None, window_title):
                        break
                logger.info("已启动被测应用: {} (工作目录: {})", app_exe, bp_dir)

            config = DesktopConfig(target_title=window_title)
            controller = DesktopController(config)

            # 获取AI客户端（如果可用）
            ai_client = None
            try:
                from src.core.ai_client import AIClient
                ai_client = AIClient()
            except Exception:
                logger.debug("AI客户端不可用，桌面测试将仅使用UI Automation")

            runner = DesktopBlueprintRunner(
                controller=controller,
                ai_client=ai_client,
            )
            report = await runner.run(blueprint)

            await controller.close()

            from src.api.models import StepDetail, BugDetail
            pass_rate = report.passed_steps / report.total_steps * 100 if report.total_steps > 0 else 0
            response = TestReportResponse(
                test_name=report.test_name,
                url=report.url or "",
                total_steps=report.total_steps,
                passed_steps=report.passed_steps,
                failed_steps=report.failed_steps,
                bug_count=len(report.bugs),
                pass_rate=pass_rate,
                duration_seconds=report.duration_seconds,
                report_markdown=report.report_markdown,
                steps=[
                    StepDetail(
                        step=r.step,
                        action=r.action.value if hasattr(r.action, 'value') else str(r.action),
                        description=r.description,
                        status=r.status.value if hasattr(r.status, 'value') else str(r.status),
                        duration_seconds=r.duration_seconds,
                        error_message=r.error_message,
                        screenshot_path=r.screenshot_path,
                    )
                    for r in report.step_results
                ],
                bugs=[
                    BugDetail(
                        severity=b.severity.value if hasattr(b.severity, 'value') else str(b.severity),
                        title=b.title,
                        description=b.description,
                        category=b.category,
                        location=b.location,
                        step_number=b.step_number,
                        screenshot_path=b.screenshot_path,
                    )
                    for b in report.bugs
                ],
            )
            try:
                report_dict = response.model_dump()
            except AttributeError:
                report_dict = response.dict()
            try:
                await ws_manager.send_test_done(pass_rate, len(report.bugs), full_report=report_dict)
            except Exception as ws_err:
                logger.warning("WS推送test_done失败: {}", str(ws_err)[:100])
            return response
        except HTTPException:
            raise
        except Exception as e:
            logger.error("桌面蓝本测试执行失败: {}", e)
            raise HTTPException(status_code=500, detail=f"桌面蓝本测试执行失败: {e}")

    # ── 蓝本列表与批量执行（v10.2）───────────────────────

    @router.get("/blueprint/list", response_model=BlueprintListResponse, tags=["蓝本管理"])
    async def list_blueprints(directory: str) -> BlueprintListResponse:
        """扫描目录下所有蓝本文件，返回摘要列表。

        扫描规则：
        1. 目录下的 testpilot.json
        2. 目录下 testpilot/ 子目录中的 *.testpilot.json
        3. 目录下 testpilot/ 子目录中的 testpilot.json
        """
        import glob
        from pathlib import Path

        dir_path = Path(directory)
        if not dir_path.exists():
            raise HTTPException(status_code=400, detail=f"目录不存在: {directory}")

        bp_files = []

        # 规则1: 根目录 testpilot.json
        root_bp = dir_path / "testpilot.json"
        if root_bp.exists():
            bp_files.append(root_bp)

        # 规则2+3: testpilot/ 子目录
        tp_dir = dir_path / "testpilot"
        if tp_dir.is_dir():
            for f in sorted(tp_dir.glob("*.testpilot.json")):
                bp_files.append(f)
            tp_json = tp_dir / "testpilot.json"
            if tp_json.exists() and tp_json not in bp_files:
                bp_files.append(tp_json)

        summaries = []
        for bp_file in bp_files:
            try:
                bp = BlueprintParser.parse_file(str(bp_file))
                summaries.append(BlueprintSummary(
                    file_path=str(bp_file),
                    file_name=bp_file.name,
                    app_name=bp.app_name,
                    description=bp.description,
                    platform=bp.platform,
                    version=bp.version,
                    scenario_count=bp.total_scenarios,
                    step_count=bp.total_steps,
                ))
            except Exception as e:
                logger.warning("解析蓝本失败 {}: {}", bp_file, e)
                summaries.append(BlueprintSummary(
                    file_path=str(bp_file),
                    file_name=bp_file.name,
                    description=f"解析失败: {e}",
                ))

        return BlueprintListResponse(blueprints=summaries, total=len(summaries))

    @router.post("/test/blueprint-batch", response_model=BatchTestReportResponse, tags=["测试"])
    async def run_blueprint_batch(req: RunBlueprintBatchRequest) -> BatchTestReportResponse:
        """批量执行多个蓝本测试，按顺序依次执行，汇总报告。

        支持混合平台蓝本（web/miniprogram/desktop/android），
        根据每个蓝本的 platform 字段自动分发到对应的测试端点。
        """
        import time as _time
        from pathlib import Path

        results: list[BatchReportItem] = []
        total_start = _time.time()

        for bp_path in req.blueprint_paths:
            bp_file = Path(bp_path)
            if not bp_file.exists():
                results.append(BatchReportItem(
                    blueprint_path=bp_path,
                    app_name="未知",
                    platform="unknown",
                    total_steps=0, passed_steps=0, failed_steps=0,
                    bug_count=0, pass_rate=0, duration_seconds=0,
                    report_markdown=f"❌ 蓝本文件不存在: {bp_path}",
                ))
                continue

            try:
                blueprint = BlueprintParser.parse_file(str(bp_file))
                platform = blueprint.platform or "web"

                # 根据平台分发到对应端点（复用内部逻辑）
                if platform == "web":
                    endpoint_url = "/test/blueprint"
                    payload = {"blueprint_path": bp_path, "base_url": req.base_url}
                elif platform == "miniprogram":
                    endpoint_url = "/test/miniprogram-blueprint"
                    payload = {"blueprint_path": bp_path, "base_url": req.base_url}
                elif platform == "desktop":
                    endpoint_url = "/test/desktop-blueprint"
                    payload = {"blueprint_path": bp_path, "base_url": req.base_url}
                elif platform in ("android", "ios"):
                    endpoint_url = "/test/mobile-blueprint"
                    payload = {"blueprint_path": bp_path, "base_url": req.base_url, "mobile_session_id": ""}
                else:
                    endpoint_url = "/test/blueprint"
                    payload = {"blueprint_path": bp_path, "base_url": req.base_url}

                # 直接内部调用对应函数（避免HTTP自调用）
                import urllib.request
                import urllib.error

                body = json.dumps(payload).encode("utf-8")
                internal_req = urllib.request.Request(
                    f"http://127.0.0.1:8900/api/v1{endpoint_url}",
                    data=body,
                    headers={"Content-Type": "application/json"},
                )
                with urllib.request.urlopen(internal_req, timeout=600) as resp:
                    data = json.loads(resp.read().decode("utf-8"))

                results.append(BatchReportItem(
                    blueprint_path=bp_path,
                    app_name=data.get("test_name", blueprint.app_name),
                    platform=platform,
                    total_steps=data.get("total_steps", 0),
                    passed_steps=data.get("passed_steps", 0),
                    failed_steps=data.get("failed_steps", 0),
                    bug_count=data.get("bug_count", 0),
                    pass_rate=data.get("pass_rate", 0),
                    duration_seconds=data.get("duration_seconds", 0),
                    report_markdown=data.get("report_markdown", ""),
                ))

            except Exception as e:
                logger.error("批量测试-蓝本执行失败 {}: {}", bp_path, e)
                results.append(BatchReportItem(
                    blueprint_path=bp_path,
                    app_name=bp_file.stem,
                    platform="unknown",
                    total_steps=0, passed_steps=0, failed_steps=0,
                    bug_count=0, pass_rate=0, duration_seconds=0,
                    report_markdown=f"❌ 执行异常: {e}",
                ))

        total_duration = _time.time() - total_start
        total_steps = sum(r.total_steps for r in results)
        passed_steps = sum(r.passed_steps for r in results)
        failed_steps = sum(r.failed_steps for r in results)
        total_bugs = sum(r.bug_count for r in results)
        passed_bps = sum(1 for r in results if r.bug_count == 0 and r.total_steps > 0)
        failed_bps = len(results) - passed_bps
        overall_rate = (passed_steps / total_steps * 100) if total_steps > 0 else 0

        # 生成汇总Markdown
        lines = [
            f"# 批量蓝本测试汇总报告",
            f"",
            f"- **蓝本数**: {len(results)}（通过 {passed_bps} / 失败 {failed_bps}）",
            f"- **总步骤**: {total_steps}（通过 {passed_steps} / 失败 {failed_steps}）",
            f"- **总Bug数**: {total_bugs}",
            f"- **总通过率**: {overall_rate:.0f}%",
            f"- **总耗时**: {total_duration:.1f}秒",
            f"",
        ]
        for i, r in enumerate(results, 1):
            status = "✅" if r.bug_count == 0 and r.total_steps > 0 else "❌"
            lines.append(f"## {i}. {status} {r.app_name}（{r.platform}）")
            lines.append(f"- 通过率: {r.pass_rate:.0f}% | Bug数: {r.bug_count} | 耗时: {r.duration_seconds:.1f}s")
            lines.append("")

        return BatchTestReportResponse(
            total_blueprints=len(results),
            passed_blueprints=passed_bps,
            failed_blueprints=failed_bps,
            total_steps=total_steps,
            passed_steps=passed_steps,
            failed_steps=failed_steps,
            total_bugs=total_bugs,
            overall_pass_rate=overall_rate,
            total_duration_seconds=total_duration,
            results=results,
            summary_markdown="\n".join(lines),
        )

    # ── 快速探索（意外模式）───────────────────────────

    @router.post("/test/explore", response_model=TestReportResponse, tags=["测试"])
    async def explore_test(req: ExploreRequest) -> TestReportResponse:
        """快速探索测试：AI自动发现可交互元素并快速操作。

        不需要蓝本，Playwright自动发现按钮/输入框/链接，
        快速依次操作并截图，最后批量交给AI分析。
        """
        # 确保浏览器已启动
        if browser_automator._page is None:
            try:
                await browser_automator.launch()
            except BrowserError as e:
                raise HTTPException(status_code=500, detail=f"浏览器启动失败: {e}")

        explorer = PageExplorer(browser_automator, ai_client)

        try:
            await ws_manager.send_log(f"快速探索开始: {req.url}")
            report = await explorer.explore(
                url=req.url,
                description=req.description,
                max_actions=req.max_actions,
            )
            try:
                await ws_manager.send_test_done(
                    report.passed_steps / report.total_steps * 100 if report.total_steps > 0 else 0,
                    len(report.bugs),
                )
            except Exception as ws_err:
                logger.warning("WS推送test_done失败: {}", str(ws_err)[:100])

            return TestReportResponse(
                test_name=report.test_name,
                url=report.url,
                total_steps=report.total_steps,
                passed_steps=report.passed_steps,
                failed_steps=report.failed_steps,
                bug_count=len(report.bugs),
                pass_rate=report.passed_steps / report.total_steps * 100 if report.total_steps > 0 else 0,
                duration_seconds=report.duration_seconds,
                report_markdown=report.report_markdown,
            )
        except Exception as e:
            logger.error("快速探索执行失败: {}", e)
            raise HTTPException(status_code=500, detail=f"快速探索执行失败: {e}")

    # ── 蓝本自动生成（v10.1）───────────────────────────

    @router.post("/blueprint/generate", response_model=GenerateBlueprintResponse, tags=["蓝本生成"])
    async def generate_blueprint(req: GenerateBlueprintRequest) -> GenerateBlueprintResponse:
        """蓝本自动生成：输入 URL，自动爬取页面并生成 testpilot.json。

        流程：访问 URL → 提取元素 → 截图 → AI 分析生成蓝本
        """
        from src.testing.blueprint_generator import BlueprintGenerator

        generator = BlueprintGenerator(ai_client=ai_client)
        try:
            blueprint = await generator.from_url(
                url=req.url,
                app_name=req.app_name,
                description=req.description,
                output_path=req.output_path or None,
                platform=req.platform or "web",
            )
            return GenerateBlueprintResponse(
                success=True,
                app_name=blueprint.app_name,
                base_url=blueprint.base_url,
                total_scenarios=blueprint.total_scenarios,
                total_steps=blueprint.total_steps,
                blueprint_json=blueprint.model_dump(exclude_none=True),
                saved_path=req.output_path or "",
            )
        except Exception as e:
            logger.error("蓝本自动生成失败: {}", e)
            raise HTTPException(status_code=500, detail=f"蓝本生成失败: {e}")

    # ── 记忆系统 ──────────────────────────────────────

    @router.get("/memory/history", tags=["记忆"])
    async def get_test_history(url: str = "", limit: int = 20) -> list[dict]:
        """查询测试历史记录。"""
        if memory_store is None:
            return []
        return memory_store.get_history(url=url or None, limit=limit)

    @router.get("/memory/stats", tags=["记忆"])
    async def get_memory_stats() -> dict:
        """获取记忆系统统计信息。"""
        if memory_store is None:
            return {"total_tests": 0, "total_experiences": 0, "known_pages": 0}
        return memory_store.get_stats()

    @router.get("/memory/page/{url:path}", tags=["记忆"])
    async def get_page_info(url: str) -> dict:
        """查询页面的历史测试信息。"""
        if memory_store is None:
            return {}
        fp = memory_store.get_page_fingerprint(url)
        return fp or {}

    # ── 报告分析（v5.2）──────────────────────────────

    @router.get("/analytics/trend", tags=["报告分析"])
    async def get_pass_rate_trend(url: str = "", limit: int = 50) -> dict:
        """获取通过率趋势数据（折线图）。"""
        if memory_store is None:
            return {"labels": [], "pass_rates": [], "count": 0}
        from src.testing.report_analytics import ReportAnalytics
        return ReportAnalytics(memory_store).get_pass_rate_trend(url=url or None, limit=limit)

    @router.get("/analytics/timeline/{test_id}", tags=["报告分析"])
    async def get_screenshot_timeline(test_id: int) -> dict:
        """获取单次测试的截图时间线。"""
        if memory_store is None:
            return {"steps": [], "error": "记忆系统未初始化"}
        from src.testing.report_analytics import ReportAnalytics
        return ReportAnalytics(memory_store).get_screenshot_timeline(test_id)

    @router.get("/analytics/heatmap", tags=["报告分析"])
    async def get_bug_heatmap(url: str = "", limit: int = 100) -> dict:
        """获取Bug热力图数据。"""
        if memory_store is None:
            return {"total_bugs": 0, "by_page": [], "by_category": [], "by_severity": {}, "by_location": []}
        from src.testing.report_analytics import ReportAnalytics
        return ReportAnalytics(memory_store).get_bug_heatmap(url=url or None, limit=limit)

    @router.get("/analytics/compare", tags=["报告分析"])
    async def compare_reports(id_a: int, id_b: int) -> dict:
        """对比两次测试报告。"""
        if memory_store is None:
            return {"error": "记忆系统未初始化"}
        from src.testing.report_analytics import ReportAnalytics
        return ReportAnalytics(memory_store).compare_reports(id_a, id_b)

    @router.get("/analytics/export/{test_id}", tags=["报告分析"])
    async def export_html_report(test_id: int):
        """导出HTML可视化报告。"""
        if memory_store is None:
            from fastapi.responses import HTMLResponse
            return HTMLResponse("<html><body>记忆系统未初始化</body></html>")
        from fastapi.responses import HTMLResponse
        from src.testing.report_analytics import ReportAnalytics
        html = ReportAnalytics(memory_store).export_html_report(test_id)
        return HTMLResponse(content=html)

    # ── 实时观看（v0.7）──────────────────────────────

    @router.get("/live/vnc", tags=["实时观看"])
    async def get_vnc_info() -> dict:
        """获取 VNC 连接信息。"""
        info = live_view.get_vnc_info()
        return info.model_dump()

    @router.get("/live/screenshot", tags=["实时观看"])
    async def get_live_screenshot() -> dict:
        """获取最新截图（降级方案）。"""
        frame = await live_view.get_latest_screenshot()
        if frame is None:
            return {"available": False, "message": "暂无截图"}
        return {
            "available": True,
            "timestamp": frame.timestamp,
            "image_base64": frame.image_base64,
        }

    # ── 测试控制（v2.0）──────────────────────────────

    @router.get("/test/status", tags=["测试控制"])
    async def get_test_status() -> dict:
        """获取当前测试状态和进度。"""
        return test_controller.status_dict()

    @router.post("/test/control", tags=["测试控制"])
    async def control_test(action: str, step_delay: float | None = None) -> dict:
        """控制测试执行。

        Args:
            action: 控制动作（pause/resume/stop/step_mode_on/step_mode_off）
            step_delay: 可选，设置观看延迟秒数
        """
        result = {"action": action, "success": False, "state": ""}

        if action == "pause":
            result["success"] = test_controller.pause()
        elif action == "resume":
            result["success"] = test_controller.resume()
        elif action == "stop":
            result["success"] = test_controller.stop()
        elif action == "step_mode_on":
            test_controller.set_step_mode(True)
            result["success"] = True
        elif action == "step_mode_off":
            test_controller.set_step_mode(False)
            result["success"] = True
        else:
            raise HTTPException(status_code=400, detail=f"未知控制动作: {action}")

        if step_delay is not None:
            test_controller.set_step_delay(step_delay)

        result["state"] = test_controller.state.value
        await ws_manager.send_state_change(
            test_controller.state.value,
            test_controller.status_dict(),
        )
        return result

    # 注册WebSocket控制命令回调
    async def _handle_ws_control(action: str, data: dict) -> None:
        """WebSocket控制命令处理（与HTTP API共用逻辑）。"""
        if action == "pause":
            test_controller.pause()
        elif action == "resume":
            test_controller.resume()
        elif action == "stop":
            test_controller.stop()
        elif action == "step_mode_on":
            test_controller.set_step_mode(True)
        elif action == "step_mode_off":
            test_controller.set_step_mode(False)
        elif action == "set_delay":
            delay = data.get("seconds", 0)
            test_controller.set_step_delay(float(delay))

        await ws_manager.send_state_change(
            test_controller.state.value,
            test_controller.status_dict(),
        )

    ws_manager.set_control_callback(_handle_ws_control)

    # ── 三AI交叉验证（v3.0）────────────────────────

    @router.post("/test/generate-data", tags=["三AI验证"])
    async def generate_test_data(
        app_description: str = "",
        page_url: str = "",
        test_focus: str = "核心功能",
        input_fields: str = "",
    ) -> dict:
        """AI-B角色：独立生成测试数据。

        使用独立的AI角色生成测试输入数据，避免自我一致性偏差。
        """
        if ai_client is None:
            raise HTTPException(status_code=503, detail="AI 客户端未配置")

        validator = CrossValidator(ai_client)
        data = validator.generate_test_data(
            app_description=app_description,
            page_url=page_url,
            test_focus=test_focus,
            input_fields=input_fields,
        )
        return data

    @router.post("/test/review", tags=["三AI验证"])
    async def review_analyses(req: dict) -> dict:
        """AI-C角色：审查多次分析结果，最终仲裁。

        Body:
            analyses: list[dict] - 多次分析结果摘要
            step_description: str - 测试步骤描述
        """
        if ai_client is None:
            raise HTTPException(status_code=503, detail="AI 客户端未配置")

        validator = CrossValidator(ai_client)
        result = validator.review_analyses(
            analyses_summary=req.get("analyses", []),
            step_description=req.get("step_description", ""),
        )
        return result

    # ── 应用进程管理（v2.0-beta）─────────────────────

    # 连接process_runner的WebSocket广播
    process_runner._ws_broadcast = ws_manager.broadcast

    @router.post("/app/start", tags=["应用进程"])
    async def start_app(command: str, cwd: str = ".") -> dict:
        """启动被测应用进程。

        Args:
            command: 启动命令，如 "npm start"
            cwd: 工作目录
        """
        success = await process_runner.start(command, cwd)
        if not success:
            raise HTTPException(status_code=400, detail="进程启动失败或已在运行")
        return process_runner.status_dict()

    @router.post("/app/stop", tags=["应用进程"])
    async def stop_app() -> dict:
        """停止被测应用进程。"""
        await process_runner.stop()
        return process_runner.status_dict()

    @router.get("/app/status", tags=["应用进程"])
    async def get_app_status() -> dict:
        """获取应用进程状态。"""
        return process_runner.status_dict()

    @router.get("/app/logs", tags=["应用进程"])
    async def get_app_logs(count: int = 50) -> dict:
        """获取应用终端日志。

        Args:
            count: 返回最近N条日志
        """
        return {
            "logs": process_runner.get_recent_logs(count),
            "total": len(process_runner._buffer),
        }

    # ── Webhook 通知（v4.0）────────────────────────

    @router.post("/notify/webhook", tags=["通知"])
    async def send_webhook(req: dict) -> dict:
        """发送Webhook通知。

        Body:
            type: "dingtalk" | "feishu" | "slack" | "generic"
            webhook_url: Webhook地址
            report: 测试报告数据
        """
        from src.notify.webhook import WebhookNotifier

        notifier = WebhookNotifier()
        notify_type = req.get("type", "generic")
        webhook_url = req.get("webhook_url", "")
        report = req.get("report", {})

        if not webhook_url:
            raise HTTPException(status_code=400, detail="webhook_url 不能为空")

        handlers = {
            "dingtalk": notifier.send_dingtalk,
            "feishu": notifier.send_feishu,
            "slack": notifier.send_slack,
            "generic": notifier.send_generic,
        }

        handler = handlers.get(notify_type, notifier.send_generic)
        success = handler(webhook_url, report)
        return {"success": success, "type": notify_type}

    # ── 手机测试（v5.0）─────────────────────────────

    # 设备会话管理（内存中缓存）
    _mobile_sessions: dict[str, "AndroidController"] = {}

    @router.get("/mobile/devices", tags=["手机测试"])
    async def list_mobile_devices() -> dict:
        """列出已连接的 Android 设备（通过 adb devices）。"""
        import subprocess
        try:
            result = subprocess.run(
                ["adb", "devices", "-l"],
                capture_output=True, text=True, timeout=5,
            )
            lines = result.stdout.strip().split("\n")[1:]  # 跳过header
            devices = []
            for line in lines:
                parts = line.split()
                if len(parts) >= 2 and parts[1] == "device":
                    info = {"serial": parts[0], "status": "connected"}
                    # 解析 model/device 等额外信息
                    for part in parts[2:]:
                        if ":" in part:
                            k, v = part.split(":", 1)
                            info[k] = v
                    devices.append(info)
            return {"devices": devices, "count": len(devices)}
        except FileNotFoundError:
            return {"devices": [], "count": 0, "error": "adb 未安装或不在PATH中"}
        except Exception as e:
            return {"devices": [], "count": 0, "error": str(e)}

    @router.get("/mobile/appium/status", tags=["手机测试"])
    async def appium_status() -> dict:
        """检查 Appium Server 是否运行。"""
        import urllib.request
        import urllib.error

        appium_url = "http://127.0.0.1:4723/status"
        try:
            req = urllib.request.Request(appium_url)
            with urllib.request.urlopen(req, timeout=3) as resp:
                data = json.loads(resp.read().decode())
                return {"running": True, "data": data}
        except (urllib.error.URLError, Exception):
            return {"running": False, "message": "Appium Server 未运行。请执行: appium"}

    @router.get("/mobile/precheck", tags=["手机测试"])
    async def mobile_precheck() -> dict:
        """一次性握手：检测设备 + 自动启动 Appium Server（如未运行）。

        Returns:
            {
                "ok": bool,
                "device_ok": bool,
                "appium_ok": bool,
                "message": str,  # 中文友好提示
                "device_message": str,
                "appium_message": str,
            }
        """
        from src.controller.android import AndroidController, MobileConfig
        ctrl = AndroidController(MobileConfig())

        # 第1步：检测设备
        device_result = await ctrl.check_device()
        device_ok = device_result["ok"]

        if not device_ok:
            return {
                "ok": False,
                "device_ok": False,
                "appium_ok": False,
                "message": f"手机未连接：{device_result['message']}",
                "device_message": device_result["message"],
                "appium_message": "跳过（设备未连接）",
            }

        # 第2步：确保 Appium Server 运行（未启动则自动启动）
        appium_result = await ctrl.ensure_appium_server(timeout=30)
        appium_ok = appium_result["ok"]

        if appium_ok:
            message = f"环境就绪！{device_result['message']}，{appium_result['message']}"
        else:
            message = f"Appium启动失败：{appium_result['message']}"

        return {
            "ok": device_ok and appium_ok,
            "device_ok": device_ok,
            "appium_ok": appium_ok,
            "message": message,
            "device_message": device_result["message"],
            "appium_message": appium_result["message"],
        }

    @router.post("/mobile/session/create", tags=["手机测试"])
    async def create_mobile_session(req: dict) -> dict:
        """创建手机测试会话（连接设备）。

        Body:
            device_name: 设备名称（可选）
            app_package: 应用包名（可选）
            app_activity: 启动Activity（可选）
            app_path: APK路径（可选，自动安装）
            permissions: 权限列表（可选，自动adb授权）
        """
        from src.controller.android import AndroidController, MobileConfig

        platform = req.get("platform", "Android")
        if platform.lower() == "ios":
            config = MobileConfig(
                platform_name="iOS",
                automation_name="XCUITest",
                bundle_id=req.get("bundle_id", ""),
                udid=req.get("udid", ""),
                device_name=req.get("device_name", ""),
            )
        else:
            config = MobileConfig(
                device_name=req.get("device_name", ""),
                app_package=req.get("app_package", ""),
                app_activity=req.get("app_activity", ""),
                app_path=req.get("app_path", ""),
            )

        controller = AndroidController(config)
        try:
            await controller.launch()

            # 蓝本权限批量授予
            granted = []
            permissions = req.get("permissions", [])
            app_package = req.get("app_package", "")
            if permissions and app_package:
                granted = await controller.grant_permissions(app_package, permissions)

            session_id = f"mobile_{len(_mobile_sessions) + 1}"
            _mobile_sessions[session_id] = controller
            return {
                "session_id": session_id,
                "device": controller.device_info.model_dump(),
                "permissions_granted": granted,
                "message": "手机会话创建成功",
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"连接设备失败: {e}")

    @router.post("/mobile/session/{session_id}/tap", tags=["手机测试"])
    async def mobile_tap(session_id: str, req: dict) -> dict:
        """点击手机元素。"""
        ctrl = _mobile_sessions.get(session_id)
        if not ctrl:
            raise HTTPException(status_code=404, detail="会话不存在")
        try:
            await ctrl.tap(req.get("selector", ""))
            return {"success": True}
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

    @router.post("/mobile/session/{session_id}/input", tags=["手机测试"])
    async def mobile_input(session_id: str, req: dict) -> dict:
        """在手机输入框中输入文本。"""
        ctrl = _mobile_sessions.get(session_id)
        if not ctrl:
            raise HTTPException(status_code=404, detail="会话不存在")
        try:
            await ctrl.input_text(req.get("selector", ""), req.get("text", ""))
            return {"success": True}
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

    @router.post("/mobile/session/{session_id}/swipe", tags=["手机测试"])
    async def mobile_swipe(session_id: str, req: dict) -> dict:
        """手机滑动操作。"""
        ctrl = _mobile_sessions.get(session_id)
        if not ctrl:
            raise HTTPException(status_code=404, detail="会话不存在")
        try:
            await ctrl.swipe(
                req.get("start_x", 0), req.get("start_y", 0),
                req.get("end_x", 0), req.get("end_y", 0),
                req.get("duration_ms", 300),
            )
            return {"success": True}
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

    @router.get("/mobile/session/{session_id}/screenshot", tags=["手机测试"])
    async def mobile_screenshot(session_id: str, name: str = "") -> dict:
        """截取手机屏幕。"""
        ctrl = _mobile_sessions.get(session_id)
        if not ctrl:
            raise HTTPException(status_code=404, detail="会话不存在")
        try:
            path = await ctrl.screenshot(name or "mobile_capture")
            # 返回base64用于前端显示
            import base64
            b64 = base64.b64encode(path.read_bytes()).decode()
            return {"path": str(path), "base64": b64}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/mobile/session/{session_id}/source", tags=["手机测试"])
    async def mobile_page_source(session_id: str) -> dict:
        """获取手机UI层级XML。"""
        ctrl = _mobile_sessions.get(session_id)
        if not ctrl:
            raise HTTPException(status_code=404, detail="会话不存在")
        try:
            source = await ctrl.get_page_source()
            return {"source": source}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @router.post("/mobile/session/{session_id}/navigate", tags=["手机测试"])
    async def mobile_navigate(session_id: str, req: dict) -> dict:
        """打开URL或Activity。"""
        ctrl = _mobile_sessions.get(session_id)
        if not ctrl:
            raise HTTPException(status_code=404, detail="会话不存在")
        try:
            await ctrl.navigate(req.get("target", ""))
            return {"success": True}
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

    @router.post("/mobile/session/{session_id}/back", tags=["手机测试"])
    async def mobile_back(session_id: str) -> dict:
        """按返回键。"""
        ctrl = _mobile_sessions.get(session_id)
        if not ctrl:
            raise HTTPException(status_code=404, detail="会话不存在")
        try:
            await ctrl.back()
            return {"success": True}
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

    @router.delete("/mobile/session/{session_id}", tags=["手机测试"])
    async def close_mobile_session(session_id: str) -> dict:
        """关闭手机测试会话。"""
        ctrl = _mobile_sessions.pop(session_id, None)
        if not ctrl:
            raise HTTPException(status_code=404, detail="会话不存在")
        try:
            await ctrl.close()
            return {"message": "会话已关闭"}
        except Exception as e:
            return {"message": f"关闭时出错: {e}"}

    @router.post("/mobile/session/{session_id}/analyze", tags=["手机测试"])
    async def mobile_analyze(session_id: str, req: dict = None) -> dict:
        """截图并用AI分析手机当前页面。

        Body (可选):
            context: 额外上下文描述
            expected: 预期结果（用于步骤验证模式）
        """
        ctrl = _mobile_sessions.get(session_id)
        if not ctrl:
            raise HTTPException(status_code=404, detail="会话不存在")
        if not ai_client:
            raise HTTPException(status_code=503, detail="AI客户端未配置")

        req = req or {}
        try:
            # 截图
            path = await ctrl.screenshot("ai_analyze")

            # AI分析
            from src.core.prompts import (
                SYSTEM_MOBILE_ANALYZER,
                PROMPT_MOBILE_ANALYZE,
                PROMPT_MOBILE_VERIFY_STEP,
            )

            context = req.get("context", "用户手机当前屏幕")
            expected = req.get("expected", "")

            if expected:
                prompt = PROMPT_MOBILE_VERIFY_STEP.format(
                    expected=expected,
                    action_description=req.get("action_description", ""),
                )
            else:
                prompt = PROMPT_MOBILE_ANALYZE.format(context=context)

            analysis = ai_client.analyze_screenshot(
                image_path=str(path),
                prompt=prompt,
                system_prompt=SYSTEM_MOBILE_ANALYZER,
            )

            import base64 as b64mod
            img_b64 = b64mod.b64encode(path.read_bytes()).decode()

            return {
                "screenshot_path": str(path),
                "screenshot_base64": img_b64,
                "analysis": analysis,
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"分析失败: {e}")

    @router.get("/mobile/sessions", tags=["手机测试"])
    async def list_mobile_sessions() -> dict:
        """列出所有活跃的手机测试会话（自动清理失效session）。"""
        dead_sids = []
        sessions = []
        for sid, ctrl in _mobile_sessions.items():
            if ctrl.is_session_alive():
                sessions.append({
                    "session_id": sid,
                    "device": ctrl.device_info.model_dump(),
                })
            else:
                dead_sids.append(sid)
        # 清理失效session
        for sid in dead_sids:
            logger.info("清理失效session: {}", sid)
            try:
                await _mobile_sessions[sid].close()
            except Exception:
                pass
            del _mobile_sessions[sid]
        return {"sessions": sessions, "count": len(sessions)}

    # ── 桌面测试（v7.0）─────────────────────────────

    _desktop_sessions: dict[str, "DesktopController"] = {}

    @router.get("/desktop/windows", tags=["桌面测试"])
    async def list_desktop_windows() -> dict:
        """枚举当前可见的桌面窗口。"""
        from src.controller.window_manager import WindowManager
        try:
            windows = WindowManager.enumerate_windows(visible_only=True)
            return {
                "windows": [w.to_dict() for w in windows],
                "count": len(windows),
            }
        except Exception as e:
            return {"windows": [], "count": 0, "error": str(e)}

    @router.post("/desktop/session/create", tags=["桌面测试"])
    async def create_desktop_session(req: dict) -> dict:
        """创建桌面测试会话（连接到目标窗口）。

        Body:
            target_title: 窗口标题（模糊匹配）
            target_class: 窗口类名（可选）
            target_pid: 进程ID（可选）
            target_exe: 启动exe路径（可选，自动启动后连接）
        """
        from src.controller.desktop import DesktopController
        from src.controller.window_manager import DesktopConfig

        config = DesktopConfig(
            target_title=req.get("target_title", ""),
            target_class=req.get("target_class", ""),
            target_pid=req.get("target_pid", 0),
            target_exe=req.get("target_exe", ""),
        )

        controller = DesktopController(config)
        try:
            await controller.launch()
            session_id = f"desktop_{len(_desktop_sessions) + 1}"
            _desktop_sessions[session_id] = controller
            return {
                "session_id": session_id,
                "device": controller.device_info.model_dump(),
                "hwnd": controller.target_hwnd,
                "message": "桌面会话创建成功",
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"连接窗口失败: {e}")

    @router.post("/desktop/session/{session_id}/tap", tags=["桌面测试"])
    async def desktop_tap(session_id: str, req: dict) -> dict:
        """点击桌面元素。"""
        ctrl = _desktop_sessions.get(session_id)
        if not ctrl:
            raise HTTPException(status_code=404, detail="会话不存在")
        try:
            await ctrl.tap(req.get("selector", ""))
            return {"success": True}
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

    @router.post("/desktop/session/{session_id}/input", tags=["桌面测试"])
    async def desktop_input(session_id: str, req: dict) -> dict:
        """在桌面控件中输入文本。"""
        ctrl = _desktop_sessions.get(session_id)
        if not ctrl:
            raise HTTPException(status_code=404, detail="会话不存在")
        try:
            await ctrl.input_text(req.get("selector", ""), req.get("text", ""))
            return {"success": True}
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

    @router.get("/desktop/session/{session_id}/screenshot", tags=["桌面测试"])
    async def desktop_screenshot(session_id: str, name: str = "") -> dict:
        """截取桌面窗口。"""
        ctrl = _desktop_sessions.get(session_id)
        if not ctrl:
            raise HTTPException(status_code=404, detail="会话不存在")
        try:
            path = await ctrl.screenshot(name or "desktop_capture")
            import base64
            b64 = base64.b64encode(path.read_bytes()).decode()
            return {"path": str(path), "base64": b64}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/desktop/session/{session_id}/source", tags=["桌面测试"])
    async def desktop_page_source(session_id: str) -> dict:
        """获取桌面窗口UI树。"""
        ctrl = _desktop_sessions.get(session_id)
        if not ctrl:
            raise HTTPException(status_code=404, detail="会话不存在")
        try:
            source = await ctrl.get_page_source()
            return {"source": source}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @router.post("/desktop/session/{session_id}/navigate", tags=["桌面测试"])
    async def desktop_navigate(session_id: str, req: dict) -> dict:
        """切换窗口或启动应用。"""
        ctrl = _desktop_sessions.get(session_id)
        if not ctrl:
            raise HTTPException(status_code=404, detail="会话不存在")
        try:
            await ctrl.navigate(req.get("target", ""))
            return {"success": True, "hwnd": ctrl.target_hwnd}
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

    @router.get("/desktop/session/{session_id}/text", tags=["桌面测试"])
    async def desktop_get_text(session_id: str, selector: str = "") -> dict:
        """获取桌面元素文本。"""
        ctrl = _desktop_sessions.get(session_id)
        if not ctrl:
            raise HTTPException(status_code=404, detail="会话不存在")
        try:
            text = await ctrl.get_text(selector)
            return {"text": text}
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

    @router.delete("/desktop/session/{session_id}", tags=["桌面测试"])
    async def close_desktop_session(session_id: str) -> dict:
        """关闭桌面测试会话。"""
        ctrl = _desktop_sessions.pop(session_id, None)
        if not ctrl:
            raise HTTPException(status_code=404, detail="会话不存在")
        try:
            await ctrl.close()
            return {"message": "桌面会话已关闭"}
        except Exception as e:
            return {"message": f"关闭时出错: {e}"}

    @router.get("/desktop/sessions", tags=["桌面测试"])
    async def list_desktop_sessions() -> dict:
        """列出所有活跃的桌面测试会话。"""
        sessions = []
        for sid, ctrl in _desktop_sessions.items():
            sessions.append({
                "session_id": sid,
                "device": ctrl.device_info.model_dump(),
                "hwnd": ctrl.target_hwnd,
            })
        return {"sessions": sessions, "count": len(sessions)}

    @router.post("/desktop/session/{session_id}/analyze", tags=["桌面测试"])
    async def desktop_analyze(session_id: str, req: dict = None) -> dict:
        """截图并用AI分析桌面当前窗口。"""
        ctrl = _desktop_sessions.get(session_id)
        if not ctrl:
            raise HTTPException(status_code=404, detail="会话不存在")
        if not ai_client:
            raise HTTPException(status_code=400, detail="AI客户端未配置")
        try:
            req = req or {}
            path = await ctrl.screenshot("desktop_analyze")
            import base64
            img_b64 = base64.b64encode(path.read_bytes()).decode()

            context = req.get("context", "用户桌面当前窗口")
            analysis = ai_client.analyze_screenshot(
                image_path=str(path),
                prompt=f"分析这个Windows桌面应用截图，描述当前界面状态。上下文：{context}",
            )
            return {
                "screenshot_path": str(path),
                "screenshot_base64": img_b64,
                "analysis": analysis,
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"分析失败: {e}")

    # ── 小程序测试（v8.0）─────────────────────────

    _miniprogram_sessions: dict[str, "MiniProgramController"] = {}

    @router.get("/miniprogram/devtools/status", tags=["小程序测试"])
    async def miniprogram_devtools_status() -> dict:
        """检查微信开发者工具是否可用。"""
        from src.controller.miniprogram import MiniProgramConfig
        config = MiniProgramConfig()
        from pathlib import Path
        found = bool(config.devtools_path) and Path(config.devtools_path).exists()
        return {
            "found": found,
            "path": config.devtools_path,
            "message": "微信开发者工具已找到" if found else "未找到微信开发者工具，请安装后重试",
        }

    @router.post("/miniprogram/session/create", tags=["小程序测试"])
    async def create_miniprogram_session(req: dict) -> dict:
        """创建小程序测试会话。

        Body:
            project_path: 小程序项目路径（必须）
            devtools_path: 开发者工具CLI路径（可选，自动检测）
            account: 微信账号（可选）
        """
        from src.controller.miniprogram import MiniProgramController, MiniProgramConfig

        config = MiniProgramConfig(
            project_path=req.get("project_path", ""),
            devtools_path=req.get("devtools_path", ""),
            account=req.get("account", ""),
        )

        controller = MiniProgramController(config)
        try:
            await controller.launch()
            session_id = f"mp_{len(_miniprogram_sessions) + 1}"
            _miniprogram_sessions[session_id] = controller
            return {
                "session_id": session_id,
                "device": controller.device_info.model_dump(),
                "message": "小程序会话创建成功",
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"连接小程序失败: {e}")

    @router.post("/miniprogram/session/{session_id}/navigate", tags=["小程序测试"])
    async def miniprogram_navigate(session_id: str, req: dict) -> dict:
        """导航到小程序页面。"""
        ctrl = _miniprogram_sessions.get(session_id)
        if not ctrl:
            raise HTTPException(status_code=404, detail="会话不存在")
        try:
            await ctrl.navigate(req.get("url", ""))
            return {"success": True}
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

    @router.post("/miniprogram/session/{session_id}/tap", tags=["小程序测试"])
    async def miniprogram_tap(session_id: str, req: dict) -> dict:
        """点击小程序元素。"""
        ctrl = _miniprogram_sessions.get(session_id)
        if not ctrl:
            raise HTTPException(status_code=404, detail="会话不存在")
        try:
            await ctrl.tap(req.get("selector", ""))
            return {"success": True}
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

    @router.post("/miniprogram/session/{session_id}/input", tags=["小程序测试"])
    async def miniprogram_input(session_id: str, req: dict) -> dict:
        """在小程序输入框中输入文本。"""
        ctrl = _miniprogram_sessions.get(session_id)
        if not ctrl:
            raise HTTPException(status_code=404, detail="会话不存在")
        try:
            await ctrl.input_text(req.get("selector", ""), req.get("text", ""))
            return {"success": True}
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

    @router.get("/miniprogram/session/{session_id}/screenshot", tags=["小程序测试"])
    async def miniprogram_screenshot(session_id: str, name: str = "") -> dict:
        """截取小程序当前页面。"""
        ctrl = _miniprogram_sessions.get(session_id)
        if not ctrl:
            raise HTTPException(status_code=404, detail="会话不存在")
        try:
            path = await ctrl.screenshot(name or "mp_capture")
            import base64
            b64 = base64.b64encode(path.read_bytes()).decode()
            return {"path": str(path), "base64": b64}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/miniprogram/session/{session_id}/source", tags=["小程序测试"])
    async def miniprogram_source(session_id: str) -> dict:
        """获取小程序当前页面 WXML 结构。"""
        ctrl = _miniprogram_sessions.get(session_id)
        if not ctrl:
            raise HTTPException(status_code=404, detail="会话不存在")
        try:
            source = await ctrl.get_page_source()
            return {"source": source}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/miniprogram/session/{session_id}/text", tags=["小程序测试"])
    async def miniprogram_get_text(session_id: str, selector: str = "") -> dict:
        """获取小程序元素文本。"""
        ctrl = _miniprogram_sessions.get(session_id)
        if not ctrl:
            raise HTTPException(status_code=404, detail="会话不存在")
        try:
            text = await ctrl.get_text(selector)
            return {"text": text}
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

    @router.get("/miniprogram/session/{session_id}/page-data", tags=["小程序测试"])
    async def miniprogram_page_data(session_id: str) -> dict:
        """获取小程序当前页面 data。"""
        ctrl = _miniprogram_sessions.get(session_id)
        if not ctrl:
            raise HTTPException(status_code=404, detail="会话不存在")
        try:
            data = await ctrl.get_page_data()
            return {"data": data}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @router.delete("/miniprogram/session/{session_id}", tags=["小程序测试"])
    async def close_miniprogram_session(session_id: str) -> dict:
        """关闭小程序测试会话。"""
        ctrl = _miniprogram_sessions.pop(session_id, None)
        if not ctrl:
            raise HTTPException(status_code=404, detail="会话不存在")
        try:
            await ctrl.close()
            return {"message": "小程序会话已关闭"}
        except Exception as e:
            return {"message": f"关闭时出错: {e}"}

    @router.get("/miniprogram/sessions", tags=["小程序测试"])
    async def list_miniprogram_sessions() -> dict:
        """列出所有活跃的小程序测试会话。"""
        sessions = []
        for sid, ctrl in _miniprogram_sessions.items():
            sessions.append({
                "session_id": sid,
                "device": ctrl.device_info.model_dump(),
            })
        return {"sessions": sessions, "count": len(sessions)}

    # ── 多人协同测试（v9.0）─────────────────────────

    from src.testing.multiplayer import MultiPlayerOrchestrator

    _orchestrator = MultiPlayerOrchestrator()

    @router.post("/multiplayer/room/create", tags=["多人测试"])
    async def create_room(req: dict = None) -> dict:
        """创建多人测试房间（重置协调器）。"""
        await _orchestrator.reset()
        return {"message": "房间已创建", "max_players": _orchestrator.MAX_PLAYERS}

    @router.post("/multiplayer/room/player", tags=["多人测试"])
    async def add_player(req: dict) -> dict:
        """添加玩家到房间。

        Body: player_id, platform, config(可选)
        """
        try:
            slot = _orchestrator.add_player(
                player_id=req.get("player_id", ""),
                platform=req.get("platform", "web"),
                config=req.get("config", {}),
            )
            return {
                "player_id": slot.player_id,
                "platform": slot.platform,
                "player_count": _orchestrator.player_count,
            }
        except RuntimeError as e:
            raise HTTPException(status_code=400, detail=str(e))

    @router.delete("/multiplayer/room/player/{player_id}", tags=["多人测试"])
    async def remove_player(player_id: str) -> dict:
        """移除玩家。"""
        _orchestrator.remove_player(player_id)
        return {"message": f"已移除 {player_id}", "player_count": _orchestrator.player_count}

    @router.post("/multiplayer/room/player/{player_id}/action", tags=["多人测试"])
    async def player_action(player_id: str, req: dict) -> dict:
        """对指定玩家执行操作。

        Body: action, selector(可选), text(可选), url(可选), name(可选)
        """
        action = req.get("action", "")
        kwargs = {k: v for k, v in req.items() if k != "action"}
        try:
            result = await _orchestrator.execute_action(player_id, action, **kwargs)
            return {"success": True, "result": str(result) if result else None}
        except RuntimeError as e:
            raise HTTPException(status_code=400, detail=str(e))

    @router.post("/multiplayer/room/parallel", tags=["多人测试"])
    async def parallel_actions(req: dict) -> dict:
        """并行执行多个玩家操作。

        Body: actions: [{player, action, ...}, ...]
        """
        actions = req.get("actions", [])
        results = await _orchestrator.execute_parallel(actions)
        return {
            "results": [
                str(r) if not isinstance(r, Exception) else f"错误: {r}"
                for r in results
            ],
        }

    @router.post("/multiplayer/room/sync", tags=["多人测试"])
    async def sync_barrier(req: dict = None) -> dict:
        """触发同步屏障。"""
        req = req or {}
        name = req.get("name", "default")
        timeout = req.get("timeout", 30)
        ok = await _orchestrator.sync_all(name, timeout)
        return {"synced": ok, "name": name}

    @router.post("/multiplayer/room/screenshot-all", tags=["多人测试"])
    async def screenshot_all_players(req: dict = None) -> dict:
        """所有玩家同时截图。"""
        req = req or {}
        prefix = req.get("name_prefix", "all")
        results = await _orchestrator.screenshot_all(prefix)
        return {
            "screenshots": {pid: str(path) for pid, path in results.items()},
            "count": len(results),
        }

    @router.get("/multiplayer/room/status", tags=["多人测试"])
    async def room_status() -> dict:
        """获取房间状态。"""
        return _orchestrator.get_status()

    @router.get("/multiplayer/room/timeline", tags=["多人测试"])
    async def room_timeline() -> dict:
        """获取时序轴数据。"""
        return {"timeline": _orchestrator.get_timeline()}

    @router.post("/multiplayer/room/start", tags=["多人测试"])
    async def start_test() -> dict:
        """开始多人测试。"""
        await _orchestrator.start()
        return {"message": "测试已开始", "players": list(_orchestrator.players.keys())}

    @router.post("/multiplayer/room/stop", tags=["多人测试"])
    async def stop_test() -> dict:
        """停止多人测试。"""
        await _orchestrator.stop()
        return {"message": "测试已停止", "elapsed": round(_orchestrator.elapsed, 2)}

    @router.post("/multiplayer/blueprint/run", tags=["多人测试"])
    async def run_multiplayer_blueprint(req: dict) -> dict:
        """执行多人蓝本。

        Body: blueprint (完整蓝本JSON对象)
        """
        from src.testing.multiplayer_blueprint import MultiPlayerBlueprint

        bp_data = req.get("blueprint", {})
        if not bp_data:
            raise HTTPException(status_code=400, detail="请提供 blueprint 数据")
        bp = MultiPlayerBlueprint.from_dict(bp_data)

        await _orchestrator.reset()
        for pdef in bp.player_defs:
            _orchestrator.add_player(pdef.id, pdef.platform, {
                "url": pdef.url, "device": pdef.device,
                "project_path": pdef.project_path, **pdef.extra,
            })

        await bp.execute(_orchestrator)
        return bp.get_report()

    @router.delete("/multiplayer/room", tags=["多端协同"])
    async def destroy_room() -> dict:
        """销毁房间，断开所有玩家。"""
        await _orchestrator.reset()
        return {"message": "房间已销毁"}

    # ── 多端协同 Phase2（v9.0）────────────────────

    from src.testing.ai_player import AIPlayerEngine, AIPlayerConfig, AIStrategy
    from src.testing.action_recorder import ActionRecorder, ActionReplayer
    from src.testing.consistency_checker import ConsistencyChecker

    _ai_engines: dict[str, AIPlayerEngine] = {}
    _recorder = ActionRecorder()
    _replayer: Optional[ActionReplayer] = None
    _checker = ConsistencyChecker()

    @router.post("/multiplayer/ai/start/{player_id}", tags=["多端协同-AI"])
    async def start_ai_player(player_id: str, req: dict = None) -> dict:
        """启动 AI 自动扮演指定玩家。

        Body: strategy(random/normal/boundary/explorer), max_actions, action_delay
        """
        req = req or {}
        strategy = AIStrategy(req.get("strategy", "normal"))
        config = AIPlayerConfig(
            strategy=strategy,
            max_actions=req.get("max_actions", 50),
            action_delay=req.get("action_delay", 1.0),
        )
        engine = AIPlayerEngine(config)
        _ai_engines[player_id] = engine

        import asyncio
        asyncio.create_task(engine.run_player(_orchestrator, player_id))
        return {
            "player_id": player_id,
            "strategy": strategy.value,
            "max_actions": config.max_actions,
        }

    @router.post("/multiplayer/ai/stop/{player_id}", tags=["多端协同-AI"])
    async def stop_ai_player(player_id: str) -> dict:
        """停止指定玩家的 AI 扮演。"""
        engine = _ai_engines.get(player_id)
        if engine:
            engine.stop()
            return {"player_id": player_id, "actions_done": engine.action_count}
        raise HTTPException(status_code=404, detail=f"AI玩家 {player_id} 不存在")

    @router.get("/multiplayer/ai/report/{player_id}", tags=["多端协同-AI"])
    async def ai_player_report(player_id: str) -> dict:
        """获取 AI 玩家操作报告。"""
        engine = _ai_engines.get(player_id)
        if engine:
            return engine.get_report()
        raise HTTPException(status_code=404, detail=f"AI玩家 {player_id} 不存在")

    @router.post("/multiplayer/record/start", tags=["多端协同-录制"])
    async def start_recording() -> dict:
        """开始录制操作。"""
        _recorder.start()
        return {"recording": True}

    @router.post("/multiplayer/record/stop", tags=["多端协同-录制"])
    async def stop_recording() -> dict:
        """停止录制。"""
        _recorder.stop()
        return {
            "recording": False,
            "actions": _recorder.action_count,
            "duration": round(_recorder.duration, 2),
        }

    @router.post("/multiplayer/record/action", tags=["多端协同-录制"])
    async def record_action(req: dict) -> dict:
        """录制一条操作。

        Body: player_id, action, params(可选)
        """
        if not _recorder.is_recording:
            raise HTTPException(status_code=400, detail="未在录制状态")
        recorded = _recorder.record(
            player_id=req.get("player_id", ""),
            action=req.get("action", ""),
            params=req.get("params", {}),
        )
        return {"recorded": True, "offset": round(recorded.offset, 3), "total": _recorder.action_count}

    @router.get("/multiplayer/record/export", tags=["多端协同-录制"])
    async def export_recording() -> dict:
        """导出录制为蓝本格式。"""
        return _recorder.export_blueprint()

    @router.post("/multiplayer/replay/start", tags=["多端协同-回放"])
    async def start_replay(req: dict = None) -> dict:
        """开始回放录制的操作。

        Body: speed(倍率), player_filter(可选玩家列表)
        """
        nonlocal _replayer
        req = req or {}
        actions = _recorder.actions
        if not actions:
            raise HTTPException(status_code=400, detail="无录制数据")
        _replayer = ActionReplayer(actions)

        import asyncio
        speed = req.get("speed", 1.0)
        player_filter = req.get("player_filter")
        asyncio.create_task(_replayer.replay(_orchestrator, speed, player_filter))
        return {"replaying": True, "total_actions": len(actions), "speed": speed}

    @router.post("/multiplayer/replay/stop", tags=["多端协同-回放"])
    async def stop_replay() -> dict:
        """停止回放。"""
        if _replayer:
            _replayer.stop()
            return _replayer.get_status()
        return {"replaying": False}

    @router.get("/multiplayer/replay/status", tags=["多端协同-回放"])
    async def replay_status() -> dict:
        """获取回放进度。"""
        if _replayer:
            return _replayer.get_status()
        return {"replaying": False, "total": 0, "current": 0, "progress": 0}

    @router.post("/multiplayer/consistency/check", tags=["多端协同-一致性"])
    async def consistency_check(req: dict = None) -> dict:
        """执行跨端一致性检查。

        Body: player_ids(可选, 默认全部), check_source, check_screenshot
        """
        req = req or {}
        report = await _checker.check(
            _orchestrator,
            player_ids=req.get("player_ids"),
            check_source=req.get("check_source", True),
            check_screenshot=req.get("check_screenshot", True),
        )
        return report.to_dict()

    @router.get("/multiplayer/consistency/summary", tags=["多端协同-一致性"])
    async def consistency_summary() -> dict:
        """获取一致性检查历史摘要。"""
        return _checker.get_summary()

    # ── 多端协同 Phase3（v9.0）────────────────────

    from src.testing.network_simulator import NetworkSimulator, NetworkConfig, NetworkProfile
    from src.testing.device_pool import DevicePoolManager, DeviceType, DeviceState

    _network = NetworkSimulator()
    _device_pool = DevicePoolManager()

    @router.post("/multiplayer/network/enable", tags=["多端协同-网络模拟"])
    async def enable_network_sim() -> dict:
        """启用网络模拟。"""
        _network.enable()
        return {"enabled": True}

    @router.post("/multiplayer/network/disable", tags=["多端协同-网络模拟"])
    async def disable_network_sim() -> dict:
        """禁用网络模拟。"""
        _network.disable()
        return {"enabled": False}

    @router.post("/multiplayer/network/profile", tags=["多端协同-网络模拟"])
    async def set_network_profile(req: dict) -> dict:
        """设置网络环境预设。

        Body: profile(perfect/wifi/4g/3g/slow/unstable/offline), player_id(可选)
        """
        profile = NetworkProfile(req.get("profile", "perfect"))
        config = NetworkConfig.from_profile(profile)
        player_id = req.get("player_id")
        if player_id:
            _network.set_player(player_id, config)
        else:
            _network.set_global(config)
        _network.enable()
        return {
            "profile": profile.value,
            "player_id": player_id or "全局",
            "latency_ms": config.latency_ms,
            "packet_loss": config.packet_loss,
        }

    @router.post("/multiplayer/network/custom", tags=["多端协同-网络模拟"])
    async def set_network_custom(req: dict) -> dict:
        """设置自定义网络条件。

        Body: latency_ms, jitter_ms, packet_loss, bandwidth_kbps, player_id(可选)
        """
        config = NetworkConfig(
            latency_ms=req.get("latency_ms", 0),
            jitter_ms=req.get("jitter_ms", 0),
            packet_loss=req.get("packet_loss", 0.0),
            bandwidth_kbps=req.get("bandwidth_kbps", 0),
        )
        player_id = req.get("player_id")
        if player_id:
            _network.set_player(player_id, config)
        else:
            _network.set_global(config)
        _network.enable()
        return {"player_id": player_id or "全局", "config": {
            "latency_ms": config.latency_ms, "jitter_ms": config.jitter_ms,
            "packet_loss": config.packet_loss, "bandwidth_kbps": config.bandwidth_kbps,
        }}

    @router.get("/multiplayer/network/stats", tags=["多端协同-网络模拟"])
    async def network_stats() -> dict:
        """获取网络模拟统计。"""
        return _network.get_stats()

    @router.post("/multiplayer/devices/register", tags=["多端协同-设备池"])
    async def register_device(req: dict) -> dict:
        """注册设备到池。

        Body: device_id, device_type(browser/android/ios/desktop/miniprogram), name, capabilities, tags
        """
        device = _device_pool.register(
            device_id=req.get("device_id", ""),
            device_type=DeviceType(req.get("device_type", "browser")),
            name=req.get("name", ""),
            capabilities=req.get("capabilities", {}),
            tags=req.get("tags", []),
        )
        return {"device_id": device.device_id, "type": device.device_type.value, "total": _device_pool.device_count}

    @router.delete("/multiplayer/devices/{device_id}", tags=["多端协同-设备池"])
    async def unregister_device(device_id: str) -> dict:
        """注销设备。"""
        _device_pool.unregister(device_id)
        return {"device_id": device_id, "total": _device_pool.device_count}

    @router.post("/multiplayer/devices/acquire", tags=["多端协同-设备池"])
    async def acquire_device(req: dict) -> dict:
        """为玩家分配设备。

        Body: player_id, device_type(可选), tags(可选)
        """
        dtype = DeviceType(req["device_type"]) if "device_type" in req else None
        device = _device_pool.acquire(req.get("player_id", ""), dtype, req.get("tags"))
        if device:
            return {"device_id": device.device_id, "type": device.device_type.value, "assigned_to": device.assigned_to}
        raise HTTPException(status_code=404, detail="无可用设备")

    @router.post("/multiplayer/devices/release/{device_id}", tags=["多端协同-设备池"])
    async def release_device(device_id: str) -> dict:
        """释放设备。"""
        _device_pool.release(device_id)
        return {"device_id": device_id, "state": "available"}

    @router.post("/multiplayer/devices/auto-assign", tags=["多端协同-设备池"])
    async def auto_assign_devices(req: dict) -> dict:
        """批量自动分配。

        Body: configs: [{player_id, device_type, tags}]
        """
        result = _device_pool.auto_assign(req.get("configs", []))
        return {"assignments": result}

    @router.post("/multiplayer/devices/release-all", tags=["多端协同-设备池"])
    async def release_all_devices() -> dict:
        """释放所有在用设备。"""
        count = _device_pool.release_all()
        return {"released": count}

    @router.get("/multiplayer/devices/summary", tags=["多端协同-设备池"])
    async def device_pool_summary() -> dict:
        """获取设备池摘要。"""
        return _device_pool.get_summary()

    @router.post("/multiplayer/devices/health-check", tags=["多端协同-设备池"])
    async def device_health_check(req: dict = None) -> dict:
        """设备健康检查。"""
        req = req or {}
        offline = _device_pool.check_health(req.get("timeout", 60))
        return {"offline_count": len(offline), "offline_devices": offline}

    return router
