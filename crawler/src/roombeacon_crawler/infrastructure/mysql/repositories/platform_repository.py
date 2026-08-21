import logging
from sqlalchemy import text
from roombeacon_crawler.domain.ports.persistence_port import PlatformRepositoryPort
from roombeacon_crawler.infrastructure.mysql.connection import MySQLConnectionFactory

logger = logging.getLogger(__name__)


class MySQLPlatformRepository(PlatformRepositoryPort):
    """Repository quản lý bảng platforms trong MySQL."""

    def __init__(self, connection=None) -> None:
        self.connection = connection

    def get_or_create_platform(self, source_code: str, display_name: str, base_url: str) -> int:
        conn = self.connection or MySQLConnectionFactory.get_engine().connect()
        query_find = text("SELECT id FROM platforms WHERE code = :code LIMIT 1")
        result = conn.execute(query_find, {"code": source_code}).fetchone()
        if result:
            return int(result[0])

        query_insert = text(
            """
            INSERT INTO platforms (code, name, base_url, created_at, updated_at)
            VALUES (:code, :name, :base_url, NOW(), NOW())
            ON DUPLICATE KEY UPDATE updated_at = NOW()
            """
        )
        conn.execute(
            query_insert,
            {"code": source_code, "name": display_name, "base_url": base_url},
        )
        result_new = conn.execute(query_find, {"code": source_code}).fetchone()
        return int(result_new[0]) if result_new else 1
