"""Fail-closed guards for the simplified RoomBeacon reset command."""

import gzip
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "reset_roombeacon_data.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("reset_roombeacon_data_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class ResetRoomBeaconDataSafetyTests(unittest.TestCase):
    @staticmethod
    def _runtime(data_dir: str = "/safe/roombeacon/data"):
        mysql = SimpleNamespace(host="mysql-bronze", port=3306,
            database="roombeacon_bronze", user="runtime-user",
            password="runtime-password")
        return SimpleNamespace(mysql_bronze=mysql,
            crawler=SimpleNamespace(data_dir=data_dir))

    @staticmethod
    def _zero_counts(module):
        return {table: 0 for table in module.TABLE_DELETE_ORDER}

    @staticmethod
    def _fake_dump(**kwargs):
        path = Path(kwargs["backup_dir"]) / "dump.sql.gz"
        path.parent.mkdir(parents=True)
        with gzip.open(path, "wb") as stream:
            stream.write(b"CREATE TABLE example (id INT);")
        return path

    def test_a_mode_is_mandatory_before_runtime_access(self) -> None:
        module = _load_module()
        with patch.object(module, "get_environment") as get_environment:
            with self.assertRaises(SystemExit):
                module.main([])
        get_environment.assert_not_called()

    def test_modes_are_mutually_exclusive(self) -> None:
        module = _load_module()
        with self.assertRaises(SystemExit):
            module._parse_args(["--dry-run", "--backup-only"])

    def test_trigger_requires_confirmed_reset(self) -> None:
        module = _load_module()
        with self.assertRaises(module.ResetSafetyError):
            module._parse_args(["--dry-run", "--trigger-recrawl"])

    def test_obsolete_host_replica_and_auth_options_are_rejected(self) -> None:
        module = _load_module()
        for option in ("--primary-host", "--replica-socket", "--interactive-credentials"):
            with self.subTest(option=option), self.assertRaises(SystemExit):
                module._parse_args(["--dry-run", option, "unused"])

    def test_dry_run_uses_runtime_primary_and_does_not_mutate(self) -> None:
        module = _load_module()
        runtime = self._runtime()
        with (
            patch.object(module, "get_environment", return_value=runtime),
            patch.object(module, "_verify_primary", return_value=self._zero_counts(module)) as verify,
            patch.object(module, "_create_and_verify_backup") as backup,
            patch.object(module, "_pause_and_verify_idle") as pause,
            patch.object(module, "_reset_mysql") as reset_mysql,
            patch.object(module, "_reset_filesystem") as reset_filesystem,
            patch("builtins.print") as output,
        ):
            self.assertEqual(module.main(["--dry-run"]), 0)
        verify.assert_called_once_with(runtime.mysql_bronze)
        backup.assert_not_called(); pause.assert_not_called()
        reset_mysql.assert_not_called(); reset_filesystem.assert_not_called()
        report = json.loads(output.call_args.args[0])
        self.assertFalse(report["replica_dependency"])
        self.assertFalse(report["minio_dependency"])

    def test_backup_only_does_not_pause_or_reset(self) -> None:
        module = _load_module(); runtime = self._runtime()
        backup_path = Path("/safe/roombeacon/data/backups/reset_test")
        with (
            patch.object(module, "get_environment", return_value=runtime),
            patch.object(module, "_verify_primary", return_value={}),
            patch.object(module, "_create_and_verify_backup", return_value=backup_path) as backup,
            patch.object(module, "_pause_and_verify_idle") as pause,
            patch.object(module, "_reset_mysql") as reset_mysql,
        ):
            self.assertEqual(module.main(["--backup-only"]), 0)
        backup.assert_called_once_with(Path("/safe/roombeacon/data"))
        pause.assert_not_called(); reset_mysql.assert_not_called()

    def test_confirmed_reset_orders_backup_before_destructive_work(self) -> None:
        module = _load_module(); runtime = self._runtime(); order: list[str] = []
        with (
            patch.object(module, "get_environment", return_value=runtime),
            patch.object(module, "_verify_primary", return_value={}),
            patch.object(module, "_create_and_verify_backup", side_effect=lambda *_: order.append("backup") or Path("/safe/backup")),
            patch.object(module, "_pause_and_verify_idle", side_effect=lambda: order.append("pause")),
            patch.object(module, "_reset_mysql", side_effect=lambda *_: order.append("mysql")),
            patch.object(module, "_reset_filesystem", side_effect=lambda *_: order.append("filesystem")),
            patch.object(module, "_verify_clean", side_effect=lambda *_: order.append("verify")),
        ):
            self.assertEqual(module.main(["--confirm-reset-roombeacon"]), 0)
        self.assertEqual(order, ["backup", "pause", "mysql", "filesystem", "verify"])

    def test_backup_failure_blocks_all_destructive_work(self) -> None:
        module = _load_module()
        with (
            patch.object(module, "get_environment", return_value=self._runtime()),
            patch.object(module, "_verify_primary", return_value={}),
            patch.object(module, "_create_and_verify_backup", side_effect=module.ResetSafetyError("backup failed")),
            patch.object(module, "_pause_and_verify_idle") as pause,
            patch.object(module, "_reset_mysql") as reset_mysql,
            patch.object(module, "_reset_filesystem") as reset_filesystem,
        ):
            with self.assertRaises(module.ResetSafetyError):
                module.main(["--confirm-reset-roombeacon"])
        pause.assert_not_called(); reset_mysql.assert_not_called(); reset_filesystem.assert_not_called()

    def test_configured_database_mismatch_fails_before_primary_connection(self) -> None:
        module = _load_module(); runtime = self._runtime()
        runtime.mysql_bronze.database = "wrong_database"
        with patch.object(module, "get_environment", return_value=runtime), patch.object(module, "_verify_primary") as verify:
            with self.assertRaises(module.ResetSafetyError):
                module.main(["--dry-run"])
        verify.assert_not_called()

    def test_primary_identity_mismatch_fails_closed(self) -> None:
        module = _load_module(); cursor = MagicMock()
        cursor.fetchone.return_value = {"db": "wrong_database", "read_only": 0}
        connection = MagicMock()
        connection.__enter__.return_value.cursor.return_value.__enter__.return_value = cursor
        with patch.object(module, "_mysql_connection", return_value=connection):
            with self.assertRaises(module.ResetSafetyError):
                module._verify_primary(self._runtime().mysql_bronze)

    def test_primary_unreachable_is_sanitized_and_blocks_reset(self) -> None:
        module = _load_module()
        error = module.pymysql.err.OperationalError(2003, "secret-bearing endpoint")
        with patch.object(module, "_mysql_connection", side_effect=error):
            with self.assertRaisesRegex(module.ResetSafetyError,
                    "Primary connection or authentication failed") as raised:
                module._verify_primary(self._runtime().mysql_bronze)
        self.assertNotIn("secret-bearing", str(raised.exception))

    def test_broad_data_roots_are_rejected(self) -> None:
        module = _load_module()
        with self.assertRaises(module.ResetSafetyError): module._safe_data_root("/")
        with self.assertRaises(module.ResetSafetyError): module._safe_data_root(str(Path.home()))
        self.assertEqual(module._safe_data_root("/data"), Path("/data"))

    def test_reset_scope_excludes_backups_minio_and_airflow(self) -> None:
        module = _load_module()
        self.assertEqual(set(module.FILESYSTEM_TARGETS), {"bronze", "state", "discovery", "manifests"})
        self.assertNotIn("backups", module.FILESYSTEM_TARGETS)
        self.assertNotIn("minio", module.FILESYSTEM_TARGETS)
        self.assertNotIn("airflow", module.TABLE_DELETE_ORDER)

    def test_filesystem_reset_removes_only_application_targets(self) -> None:
        module = _load_module()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "data"
            for name in (*module.FILESYSTEM_TARGETS, "backups", "minio"):
                (root / name).mkdir(parents=True); (root / name / "marker").write_text(name)
            module._reset_filesystem(root)
            self.assertTrue((root / "backups" / "marker").is_file())
            self.assertTrue((root / "minio" / "marker").is_file())
            for name in module.FILESYSTEM_TARGETS: self.assertFalse((root / name).exists())

    def test_clean_verification_rejects_nonzero_primary(self) -> None:
        module = _load_module()
        with tempfile.TemporaryDirectory() as temp, patch.object(module, "_verify_primary", return_value={"rental_posts": 1}):
            with self.assertRaises(module.ResetSafetyError):
                module._verify_clean(Path(temp), self._runtime().mysql_bronze)

    def test_clean_verification_rejects_remaining_state(self) -> None:
        module = _load_module()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); (root / "state").mkdir()
            with patch.object(module, "_verify_primary", return_value={}):
                with self.assertRaises(module.ResetSafetyError): module._verify_clean(root, self._runtime().mysql_bronze)

    def test_failed_dump_leaves_partial_unverified_manifest(self) -> None:
        module = _load_module()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "data"; root.mkdir()
            with patch.object(module, "backup_mysql_database", side_effect=RuntimeError("dump failed")):
                with self.assertRaises(RuntimeError): module._create_and_verify_backup(root)
            backup_root = next((root / "backups").iterdir())
            manifest = json.loads((backup_root / "BACKUP_MANIFEST.json").read_text())
            self.assertEqual(manifest["verification_status"], "PARTIAL_UNVERIFIED")

    def test_complete_backup_contains_mysql_and_state_without_minio(self) -> None:
        module = _load_module()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "data"; (root / "state").mkdir(parents=True)
            (root / "state" / "checkpoint.json").write_text("{}")
            with patch.object(module, "backup_mysql_database", side_effect=self._fake_dump):
                backup_root = module._create_and_verify_backup(root)
            manifest = json.loads((backup_root / "BACKUP_MANIFEST.json").read_text())
            self.assertEqual(manifest["verification_status"], "VERIFIED")
            self.assertTrue(manifest["components"]["crawler_state"])
            self.assertNotIn("minio", json.dumps(manifest).lower())
            module._verify_backup_manifest(backup_root)

    def test_backup_checksum_tampering_fails_verification(self) -> None:
        module = _load_module()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "data"; root.mkdir()
            with patch.object(module, "backup_mysql_database", side_effect=self._fake_dump):
                backup_root = module._create_and_verify_backup(root)
            next((backup_root / "mysql").iterdir()).write_bytes(b"tampered")
            with self.assertRaises(module.ResetSafetyError): module._verify_backup_manifest(backup_root)

    def test_legacy_partial_backup_is_marked_unverified(self) -> None:
        module = _load_module()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "data"; legacy = root / "backups" / "reset_legacy"; legacy.mkdir(parents=True)
            self.assertEqual(module._mark_legacy_partial_backups(root), 1)
            manifest = json.loads((legacy / "BACKUP_MANIFEST.json").read_text())
            self.assertEqual(manifest["verification_status"], "PARTIAL_UNVERIFIED")
            self.assertEqual(module._mark_legacy_partial_backups(root), 0)

    def test_recrawl_triggers_only_normal_crawler_dag(self) -> None:
        module = _load_module()
        with (
            patch.object(module, "get_environment", return_value=self._runtime()),
            patch.object(module, "_verify_primary", return_value={}),
            patch.object(module, "_create_and_verify_backup", return_value=Path("/safe/backup")),
            patch.object(module, "_pause_and_verify_idle"), patch.object(module, "_reset_mysql"),
            patch.object(module, "_reset_filesystem"), patch.object(module, "_verify_clean"),
            patch.object(module, "_run") as run,
        ):
            self.assertEqual(module.main(["--confirm-reset-roombeacon", "--trigger-recrawl"]), 0)
        self.assertEqual(run.call_args_list, [
            call(["airflow", "dags", "unpause", "roombeacon_crawler"]),
            call(["airflow", "dags", "trigger", "roombeacon_crawler"]),
        ])

    def test_script_has_no_replica_minio_or_interactive_auth_dependency(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        for obsolete in ("import boto3", "import getpass", "_verify_replica", "--primary-host"):
            self.assertNotIn(obsolete, source)


if __name__ == "__main__":
    unittest.main()
