"""Create guarded SQLAlchemy engines for the Bronze MySQL database.

This infrastructure adapter owns connection construction and test isolation. It
does not define repository queries or application transaction semantics.
"""

import logging

from roombeacon_crawler.config.env.mysql import is_test_runtime
from roombeacon_crawler.config.get_env import env
from roombeacon_crawler.domain.errors.domain_error import (
    DatabaseConnectionError,
    TestEnvironmentIsolationError,
)

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

                # Fail-closed guard: Disallow creating engine targeting production DB during test runtime
                if is_test_runtime() and mysql_cfg.database == "roombeacon_bronze":
                    raise TestEnvironmentIsolationError(
                        "FAIL-CLOSED ISOLATION GUARD: Refusing to create MySQL engine targeting production database "
                        f"'{mysql_cfg.database}' during test execution! Tests must use an isolated test database."
                    )

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
            except TestEnvironmentIsolationError:
                raise
            except Exception as exc:
                logger.error(
                    "MySQL engine initialization failed (operation=create_engine, error_class=%s)",
                    type(exc).__name__,
                )
                raise DatabaseConnectionError(
                    "MySQL engine initialization failed"
                ) from None
        return cls._engine
