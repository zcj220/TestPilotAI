"""
TestPilot AI 启动入口

使用方式：
    poetry run python main.py
    或
    poetry run uvicorn src.app:app --reload
"""

import uvicorn

from src.core.config import get_config


def main() -> None:
    """启动 TestPilot AI 核心引擎服务。"""
    config = get_config()
    uvicorn.run(
        "src.app:app",
        host=config.server.host,
        port=config.server.port,
        reload=config.server.reload,
        log_level=config.server.log_level.lower(),
    )


if __name__ == "__main__":
    main()
