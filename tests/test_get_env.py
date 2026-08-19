import os
import unittest
from unittest.mock import patch

from roombeacon_crawler.config.env.crawler import load_crawler_env
from roombeacon_crawler.config.env.loader import (
    get_bool,
    get_float,
    get_int,
    get_optional_str,
    get_str,
)
from roombeacon_crawler.config.env.minio import load_minio_env
from roombeacon_crawler.config.env.mysql import load_bronze_mysql_env
from roombeacon_crawler.config.env.project import load_project_env
from roombeacon_crawler.config.get_env import env, load_environment


class TestGetEnvHelpers(unittest.TestCase):
    def test_get_str(self) -> None:
        with patch.dict(os.environ, {"TEST_STR": "  hello world  "}):
            self.assertEqual(get_str("TEST_STR"), "hello world")

        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(get_str("TEST_STR_DEFAULT", default="fallback"), "fallback")
            self.assertIsNone(get_str("TEST_STR_NONE"))

    def test_get_str_required(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ValueError):
                get_str("TEST_MISSING", required=True)

        with patch.dict(os.environ, {"TEST_EMPTY": "   "}):
            with self.assertRaises(ValueError):
                get_str("TEST_EMPTY", required=True)

    def test_get_int(self) -> None:
        with patch.dict(os.environ, {"TEST_INT": " 8080 "}):
            self.assertEqual(get_int("TEST_INT"), 8080)

        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(get_int("TEST_INT_DEFAULT", default=3306), 3306)

    def test_get_int_invalid(self) -> None:
        with patch.dict(os.environ, {"TEST_INVALID_INT": "abc"}):
            with self.assertRaises(ValueError):
                get_int("TEST_INVALID_INT")

    def test_get_int_required_missing(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ValueError):
                get_int("TEST_MISSING_INT", required=True)

    def test_get_float(self) -> None:
        with patch.dict(os.environ, {"TEST_FLOAT": " 2.5 "}):
            self.assertEqual(get_float("TEST_FLOAT"), 2.5)

        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(get_float("TEST_FLOAT_DEFAULT", default=1.5), 1.5)

    def test_get_float_invalid(self) -> None:
        with patch.dict(os.environ, {"TEST_INVALID_FLOAT": "xyz"}):
            with self.assertRaises(ValueError):
                get_float("TEST_INVALID_FLOAT")

    def test_get_bool(self) -> None:
        truthy = ["true", "TRUE", "1", "yes", "YES", "y", "on", "ON"]
        for val in truthy:
            with patch.dict(os.environ, {"TEST_BOOL": val}):
                self.assertTrue(get_bool("TEST_BOOL"), f"Failed for {val}")

        falsy = ["false", "FALSE", "0", "no", "NO", "n", "off", "OFF"]
        for val in falsy:
            with patch.dict(os.environ, {"TEST_BOOL": val}):
                self.assertFalse(get_bool("TEST_BOOL"), f"Failed for {val}")

    def test_get_bool_invalid(self) -> None:
        with patch.dict(os.environ, {"TEST_INVALID_BOOL": "abc"}):
            with self.assertRaises(ValueError):
                get_bool("TEST_INVALID_BOOL")

    def test_get_bool_default(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            self.assertTrue(get_bool("TEST_BOOL_DEF", default=True))
            self.assertFalse(get_bool("TEST_BOOL_DEF", default=False))

    def test_get_optional_str(self) -> None:
        with patch.dict(os.environ, {"TEST_OPT": " 2026-08-19 "}):
            self.assertEqual(get_optional_str("TEST_OPT"), "2026-08-19")

        with patch.dict(os.environ, {"TEST_OPT_EMPTY": "   "}):
            self.assertIsNone(get_optional_str("TEST_OPT_EMPTY"))

        with patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(get_optional_str("TEST_OPT_UNSET"))
            self.assertEqual(get_optional_str("TEST_OPT_UNSET", default="def"), "def")


class TestDomainEnvLoaders(unittest.TestCase):
    def test_load_crawler_env(self) -> None:
        c_env = load_crawler_env()
        self.assertEqual(c_env.user_agent, "RoomBeaconCrawler/0.1")
        self.assertTrue(isinstance(c_env.max_retries, int))
        self.assertTrue(isinstance(c_env.request_timeout_seconds, float))

    def test_load_bronze_mysql_env(self) -> None:
        m_env = load_bronze_mysql_env()
        self.assertEqual(m_env.host, "mysql-bronze")
        self.assertEqual(m_env.port, 3306)
        self.assertEqual(m_env.database, "roombeacon_bronze")
        self.assertIn("mysql+pymysql://", m_env.sqlalchemy_url)

    def test_load_minio_env(self) -> None:
        minio_env = load_minio_env()
        self.assertEqual(minio_env.endpoint, "minio:9000")
        self.assertEqual(minio_env.bucket_raw, "roombeacon-raw")

    def test_load_project_env(self) -> None:
        p_env = load_project_env()
        self.assertEqual(p_env.project_name, "roombeacon")
        self.assertEqual(p_env.environment, "development")

    def test_environment_facade(self) -> None:
        self.assertIsNotNone(env.crawler)
        self.assertIsNotNone(env.mysql_bronze)
        self.assertIsNotNone(env.minio)
        self.assertIsNotNone(env.duckdb)
        self.assertIsNotNone(env.processing)
        self.assertIsNotNone(env.pipeline)
        self.assertIsNotNone(env.clickhouse)
        self.assertIsNotNone(env.backend)
        self.assertIsNotNone(env.security)

        # verify reload
        loaded = load_environment()
        self.assertEqual(loaded.project.project_name, "roombeacon")


if __name__ == "__main__":
    unittest.main()
