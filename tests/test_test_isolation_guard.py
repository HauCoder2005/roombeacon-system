import os
import unittest
from unittest.mock import patch

from roombeacon_crawler.config.env.mysql import is_test_runtime, load_bronze_mysql_env
from roombeacon_crawler.domain.errors.domain_error import TestEnvironmentIsolationError
from roombeacon_crawler.infrastructure.mysql.connection import MySQLConnectionFactory


class TestTestEnvironmentIsolationGuard(unittest.TestCase):
    """Kiểm thử cơ chế Fail-Closed bảo vệ Production Database khỏi môi trường test."""

    def test_is_test_runtime_detection(self):
        """Môi trường chạy test unittest/pytest phải được nhận diện là test runtime."""
        with patch.dict(os.environ, {"ROOMBEACON_ENV": "test"}):
            self.assertTrue(is_test_runtime())
        with patch.dict(os.environ, {"ROOMBEACON_ENV": "development"}):
            self.assertFalse(is_test_runtime())

    def test_load_bronze_mysql_env_defaults_to_test_db(self):
        """Trong môi trường test, database mặc định phải là roombeacon_bronze_test."""
        with patch.dict(os.environ, {"ROOMBEACON_ENV": "test"}, clear=False):
            # Xóa BRONZE_MYSQL_DATABASE nếu có để test default
            env_without_db = {k: v for k, v in os.environ.items() if k != "BRONZE_MYSQL_DATABASE"}
            with patch.dict(os.environ, env_without_db, clear=True):
                cfg = load_bronze_mysql_env()
                self.assertEqual(cfg.database, "roombeacon_bronze_test")

    def test_fail_closed_guard_raises_on_production_db_in_test_env(self):
        """Nếu cấu hình test cố tình trỏ vào roombeacon_bronze, hệ thống bắt buộc ném lỗi Fail-Closed."""
        with patch.dict(os.environ, {
            "ROOMBEACON_ENV": "test",
            "BRONZE_MYSQL_DATABASE": "roombeacon_bronze"
        }):
            with self.assertRaises(TestEnvironmentIsolationError):
                load_bronze_mysql_env()

    def test_connection_factory_blocks_production_db_in_test_env(self):
        """MySQLConnectionFactory bắt buộc chặn khởi tạo Engine trỏ tới production database trong test."""
        MySQLConnectionFactory._engine = None
        with patch.dict(os.environ, {"ROOMBEACON_ENV": "test"}):
            with patch("roombeacon_crawler.infrastructure.mysql.connection.env") as mock_env:
                mock_env.mysql_bronze.database = "roombeacon_bronze"
                mock_env.mysql_bronze.sqlalchemy_url = "mysql+pymysql://user:pwd@127.0.0.1:3306/roombeacon_bronze"
                with self.assertRaises(TestEnvironmentIsolationError):
                    MySQLConnectionFactory.get_engine()
        MySQLConnectionFactory._engine = None


if __name__ == "__main__":
    unittest.main()
