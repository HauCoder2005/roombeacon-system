import importlib
import importlib.util
import logging
from pathlib import Path
from types import SimpleNamespace
import sys
import tempfile
import unittest
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[1]


class TestSideEffectFreeConfiguration(unittest.TestCase):
    def tearDown(self):
        from roombeacon_crawler.config.get_env import reset_environment

        reset_environment()

    def test_importing_loader_does_not_discover_or_load_dotenv(self):
        import dotenv

        with (
            patch.object(dotenv, "find_dotenv") as find_dotenv,
            patch.object(dotenv, "load_dotenv") as load_dotenv,
        ):
            sys.modules.pop("roombeacon_crawler.config.env.loader", None)
            importlib.import_module("roombeacon_crawler.config.env.loader")

        find_dotenv.assert_not_called()
        load_dotenv.assert_not_called()

    def test_importing_config_facade_does_not_load_environment(self):
        import roombeacon_crawler.config.get_env as config

        config.reset_environment()
        self.assertIsNone(config._environment)
        self.assertEqual(repr(config.env), "<LazyEnvironment unloaded>")
        self.assertIsNone(config._environment)

    def test_explicit_test_environment_injection(self):
        import roombeacon_crawler.config.get_env as config

        test_environment = SimpleNamespace(
            project=SimpleNamespace(environment="test"),
            crawler=SimpleNamespace(data_dir="/tmp/roombeacon-explicit-test"),
        )
        config.configure_environment(test_environment)
        self.assertIs(config.get_environment(), test_environment)
        self.assertEqual(config.env.project.environment, "test")
        self.assertEqual(config.env.crawler.data_dir, "/tmp/roombeacon-explicit-test")


class TestSafeDAGImports(unittest.TestCase):
    def test_all_dags_import_without_runtime_config_access(self):
        import roombeacon_crawler.config.get_env as config

        dag_files = sorted((REPO_ROOT / "airflow" / "dags").rglob("*.py"))
        self.assertEqual(len(dag_files), 6)
        config.reset_environment()

        with patch.object(
            config,
            "load_environment",
            side_effect=AssertionError("DAG import accessed runtime configuration"),
        ):
            for index, dag_file in enumerate(dag_files):
                module_name = f"roombeacon_phase05_dag_{index}"
                spec = importlib.util.spec_from_file_location(module_name, dag_file)
                self.assertIsNotNone(spec)
                self.assertIsNotNone(spec.loader)
                module = importlib.util.module_from_spec(spec)
                sys.modules[module_name] = module
                try:
                    spec.loader.exec_module(module)
                finally:
                    sys.modules.pop(module_name, None)

        self.assertIsNone(config._environment)


class TestSafeExceptionLogging(unittest.TestCase):
    def test_local_state_log_does_not_include_file_payload(self):
        from roombeacon_crawler.repositories.local_asset_state_repository import (
            LocalAssetStateRepository,
        )

        marker = "SENSITIVE_LOCAL_STATE_MARKER"
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = LocalAssetStateRepository(base_dir=temp_dir)
            item_path = Path(temp_dir) / "source" / "asset.json"
            item_path.parent.mkdir(parents=True, exist_ok=True)
            item_path.write_text("{" + marker, encoding="utf-8")

            with self.assertLogs(
                "roombeacon_crawler.repositories.local_asset_state_repository",
                level=logging.WARNING,
            ) as captured:
                self.assertIsNone(repo.get_asset("source", "asset"))

        self.assertNotIn(marker, "\n".join(captured.output))

    def test_sitemap_log_does_not_include_raw_exception(self):
        from roombeacon_crawler.discovery.sitemap.parser import SitemapUrlsetParser

        marker = "SENSITIVE_SITEMAP_MARKER"
        with (
            patch(
                "roombeacon_crawler.discovery.sitemap.parser.ET.fromstring",
                side_effect=RuntimeError(marker),
            ),
            self.assertLogs(
                "roombeacon_crawler.discovery.sitemap.parser", level=logging.ERROR
            ) as captured,
        ):
            self.assertEqual(SitemapUrlsetParser.parse_urlset("<urlset/>"), [])

        self.assertNotIn(marker, "\n".join(captured.output))
        self.assertIn("RuntimeError", "\n".join(captured.output))


if __name__ == "__main__":
    unittest.main()
