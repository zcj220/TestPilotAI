"""
数据库引擎与会话管理（v6.0 → v13.1）

支持三驱动：
- 默认: SQLite（个人用户，零配置）
- 可选: PostgreSQL（团队/企业部署）
- 可选: MySQL（阿里云 RDS 等云数据库）

通过环境变量 DATABASE_URL 切换：
- 未设置或 sqlite:///... → SQLite 模式
- postgresql://... → PostgreSQL 模式
- mysql+pymysql://... → MySQL 模式
"""

import os
from typing import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from loguru import logger

from src.auth.models import Base
import src.community.models  # noqa: F401 — 确保社区表注册到 Base.metadata
from src.core.config import PROJECT_ROOT


def _get_database_url() -> str:
    """获取数据库URL。"""
    url = os.environ.get("DATABASE_URL", "")
    if url:
        return url
    db_path = PROJECT_ROOT / "data" / "testpilot.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{db_path}"


def _detect_driver(url: str) -> str:
    if url.startswith("sqlite"):
        return "SQLite"
    if url.startswith("mysql") or "pymysql" in url:
        return "MySQL"
    return "PostgreSQL"


def _create_engine(url: str):
    """根据URL创建对应引擎。"""
    driver = _detect_driver(url)

    if driver == "SQLite":
        engine = create_engine(
            url,
            connect_args={"check_same_thread": False},
            echo=False,
        )

        @event.listens_for(engine, "connect")
        def _set_sqlite_pragma(dbapi_conn, connection_record):
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

        return engine

    if driver == "MySQL":
        return create_engine(
            url,
            pool_size=10,
            max_overflow=20,
            pool_recycle=3600,
            pool_pre_ping=True,
            echo=False,
        )

    return create_engine(url, pool_size=10, max_overflow=20, echo=False)


_db_url = _get_database_url()
engine = _create_engine(_db_url)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)

logger.debug("Database engine initialized | {}", _detect_driver(_db_url))


def init_db() -> None:
    """创建所有表（如不存在）。"""
    Base.metadata.create_all(bind=engine)
    logger.info("Database schema synced")


def get_db() -> Generator[Session, None, None]:
    """FastAPI 依赖注入用的数据库会话生成器。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_db_session() -> Session:
    """直接获取数据库会话（非依赖注入场景）。"""
    return SessionLocal()
