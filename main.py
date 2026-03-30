"""
TestPilot AI 启动入口

使用方式：
    poetry run python main.py
    或
    poetry run uvicorn src.app:app --reload
"""

import sys

import uvicorn

from src.core.config import get_config


def main() -> None:
    """启动 TestPilot AI 核心引擎服务。"""
    config = get_config()

    if getattr(sys, "frozen", False):
        # PyInstaller 打包模式：必须传入 app 对象，不支持字符串动态导入
        from src.app import app as _app
        uvicorn.run(
            _app,
            host=config.server.host,
            port=config.server.port,
            reload=False,
            log_level=config.server.log_level.lower(),
        )
    else:
        # 开发模式：字符串方式支持 --reload 热重载
        uvicorn.run(
            "src.app:app",
            host=config.server.host,
            port=config.server.port,
            reload=config.server.reload,
            log_level=config.server.log_level.lower(),
        )


if __name__ == "__main__":
    main()
