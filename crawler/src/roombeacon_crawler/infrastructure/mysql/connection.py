import logging
from typing import Any

from roombeacon_crawler.config.get_env import env
from roombeacon_crawler.domain.errors.domain_error import DatabaseConnectionError

logger = logging.getLogger(__name__)


class MySQLConnectionFactory:
    """Quản lý kết nối cơ sở dữ liệu MySQL thông qua SQLAlchemy Engine."""

    _engine = None

    @classmethod
    def get_engine(cls):
        """Khởi tạo hoặc trả về singleton SQLAlchemy Engine."""
        if cls._engine is None:
            try:
                from sqlalchemy import create_engine

                mysql_cfg = env.mysql_bronze
                db_url = mysql_cfg.sqlalchemy_url
                cls._engine = create_engine(
                    db_url,
                    pool_size=5,
                    max_overflow=10,
                    pool_recycle=1800,
                    pool_pre_ping=True,
                )
                logger.info(
                    "Đã khởi tạo MySQL SQLAlchemy Engine (%s:%d/%s)",
                    mysql_cfg.host,
                    mysql_cfg.port,
                    mysql_cfg.database,
                )
            except Exception as exc:
                err_msg = f"Không thể khởi tạo kết nối MySQL: {exc}"
                logger.error(err_msg, exc_info=True)
                raise DatabaseConnectionError(err_msg) from exc
        return cls._engine
