"""
日志配置模块

基于 loguru 构建统一的日志系统，支持：
- 控制台彩色输出
- 文件日志轮转
- 结构化日志格式
- 按模块过滤日志级别
"""

import sys
from pathlib import Path

from loguru import logger

from src.core.config import PROJECT_ROOT


# 日志文件存储目录
LOG_DIR = PROJECT_ROOT / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)


def setup_logger(log_level: str = "INFO", debug: bool = False) -> None:
    """初始化日志系统。

    Args:
        log_level: 日志级别，如 DEBUG / INFO / WARNING / ERROR
        debug: 是否为调试模式（启用更详细的输出格式）
    """
    # 移除 loguru 默认的 handler
    logger.remove()

    # 控制台输出格式
    console_format = (
        "<green>{time:HH:mm:ss}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
        "<level>{message}</level>"
    )
    if not debug:
        console_format = (
            "<green>{time:HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<level>{message}</level>"
        )

    # 添加控制台 handler
    logger.add(
        sys.stderr,
        format=console_format,
        level=log_level,
        colorize=True,
        backtrace=True,
        diagnose=debug,
    )

    # 添加文件 handler（每天轮转，保留30天）
    logger.add(
        LOG_DIR / "testpilot_{time:YYYY-MM-DD}.log",
        format=(
            "{time:YYYY-MM-DD HH:mm:ss.SSS} | "
            "{level: <8} | "
            "{name}:{function}:{line} | "
            "{message}"
        ),
        level="DEBUG",
        rotation="00:00",
        retention="30 days",
        compression="zip",
        encoding="utf-8",
        backtrace=True,
        diagnose=True,
    )

    # 添加错误专用日志文件
    logger.add(
        LOG_DIR / "errors_{time:YYYY-MM-DD}.log",
        format=(
            "{time:YYYY-MM-DD HH:mm:ss.SSS} | "
            "{level: <8} | "
            "{name}:{function}:{line} | "
            "{message}\n{exception}"
        ),
        level="ERROR",
        rotation="00:00",
        retention="90 days",
        compression="zip",
        encoding="utf-8",
        backtrace=True,
        diagnose=True,
    )

    logger.info("Logging system initialized | level={} | debug_mode={}", log_level, debug)
