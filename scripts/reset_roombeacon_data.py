"""Back up and reset crawler data through the existing RoomBeacon runtime.

Run this command inside the application/Airflow container. It never loads
dotenv, verifies the writable Bronze primary, and does not access replica or
MinIO infrastructure.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

import pymysql

from roombeacon_crawler.config.get_env import get_environment
from roombeacon_crawler.infrastructure.tools.backup_mysql import backup_mysql_database


EXPECTED_DATABASE = "roombeacon_bronze"
MUTATING_DAGS = (
    "roombeacon_crawler",
    "roombeacon_bronze_reconciler",
    "roombeacon_asset_reconciler",
)
TABLE_DELETE_ORDER = (
    "post_status_history", "post_attributes", "post_contacts", "post_fees",
    "post_amenities", "post_images", "post_details", "post_addresses",
    "post_prices", "rental_post_versions", "rental_posts", "platforms",
)
FILESYSTEM_TARGETS = ("bronze", "state", "discovery", "manifests")


class ResetSafetyError(RuntimeError):
    """Raised when a reset precondition or verification cannot be proven."""


def _run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, check=True, capture_output=True, text=True)


def _safe_data_root(raw: str) -> Path:
    root = Path(raw).resolve()
    forbidden = {Path("/").resolve(), Path.home().resolve()}
    if root in forbidden or (len(root.parts) < 3 and root != Path("/data")):
        raise ResetSafetyError("Configured data root is too broad for reset")
    return root


def _mysql_connection(config) -> pymysql.Connection:
    return pymysql.connect(
        host=config.host,
        port=config.port,
        user=config.user,
        password=config.password,
        database=config.database,
        cursorclass=pymysql.cursors.DictCursor,
        connect_timeout=5,
        autocommit=False,
    )


def _table_counts(cursor) -> dict[str, int]:
    counts: dict[str, int] = {}
    for table in TABLE_DELETE_ORDER:
        cursor.execute(f"SELECT COUNT(*) AS count FROM `{table}`")
        counts[table] = int(cursor.fetchone()["count"])
    return counts


def _verify_primary(config) -> dict[str, int]:
    """Verify the configured target is the writable RoomBeacon primary."""
    try:
        with _mysql_connection(config) as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT DATABASE() AS db, @@read_only AS read_only")
                identity = cursor.fetchone()
                if identity["db"] != EXPECTED_DATABASE or bool(identity["read_only"]):
                    raise ResetSafetyError(
                        "Target is not writable RoomBeacon Bronze primary"
                    )
                cursor.execute("SHOW TABLES")
                existing = {next(iter(row.values())) for row in cursor.fetchall()}
                if set(TABLE_DELETE_ORDER) - existing:
                    raise ResetSafetyError(
                        "RoomBeacon Bronze schema identity check failed"
                    )
                return _table_counts(cursor)
    except pymysql.MySQLError:
        raise ResetSafetyError("Primary connection or authentication failed") from None


def _pause_and_verify_idle() -> None:
    for dag_id in MUTATING_DAGS:
        _run(["airflow", "dags", "pause", dag_id])
    for dag_id in MUTATING_DAGS:
        result = _run([
            "airflow", "dags", "list-runs", dag_id,
            "--state", "running", "--output", "json",
        ])
        try:
            out_str = result.stdout or "[]"
            # Extract JSON from stdout which may contain warnings
            json_str = next((line for line in out_str.splitlines() if line.startswith("[") or line.startswith("{")), "[]")
            active = json.loads(json_str)
        except (json.JSONDecodeError, StopIteration) as exc:
            raise ResetSafetyError(f"Cannot verify active Airflow runs: {result.stdout}") from exc
        if active:
            raise ResetSafetyError(f"Mutating DAG still has active runs: {dag_id}")


def _copy_optional(source: Path, destination: Path) -> bool:
    if not source.exists():
        return False
    shutil.copytree(source, destination, symlinks=False)
    return True


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _verify_backup_manifest(backup_root: Path) -> None:
    manifest_path = backup_root / "BACKUP_MANIFEST.json"
    checksum_path = backup_root / "SHA256SUMS.json"
    if not manifest_path.is_file() or not checksum_path.is_file():
        raise ResetSafetyError("Backup manifest or checksum inventory is missing")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    checksums = json.loads(checksum_path.read_text(encoding="utf-8"))
    if manifest.get("verification_status") != "VERIFIED":
        raise ResetSafetyError("Backup set is not VERIFIED")
    for relative_path, expected in checksums.items():
        path = backup_root / relative_path
        if not path.is_file() or _sha256(path) != expected:
            raise ResetSafetyError("Backup checksum verification failed")


def _mark_legacy_partial_backups(data_root: Path) -> int:
    backups_root = data_root / "backups"
    if not backups_root.is_dir():
        return 0
    marked = 0
    for backup_root in backups_root.glob("reset_*"):
        manifest_path = backup_root / "BACKUP_MANIFEST.json"
        if not backup_root.is_dir() or manifest_path.exists():
            continue
        manifest_path.write_text(json.dumps({
            "timestamp_utc": None,
            "database": EXPECTED_DATABASE,
            "verification_status": "PARTIAL_UNVERIFIED",
            "components": {},
            "note": "Legacy partial backup; no completed verification manifest",
        }, indent=2), encoding="utf-8")
        marked += 1
    return marked


def _create_and_verify_backup(data_root: Path) -> Path:
    """Back up MySQL and crawler state; leave a partial marker on failure."""
    _mark_legacy_partial_backups(data_root)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_root = data_root / "backups" / f"reset_{timestamp}"
    backup_root.mkdir(parents=True, exist_ok=False)
    manifest_path = backup_root / "BACKUP_MANIFEST.json"
    base_manifest = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "database": EXPECTED_DATABASE,
        "verification_status": "PARTIAL_UNVERIFIED",
        "components": {},
    }
    manifest_path.write_text(json.dumps(base_manifest, indent=2), encoding="utf-8")

    mysql_dump = backup_mysql_database(
        database_name=EXPECTED_DATABASE,
        backup_dir=backup_root / "mysql",
        compress=True,
    )
    copied = {
        name: _copy_optional(data_root / name, backup_root / name)
        for name in ("state", "discovery", "manifests")
    }
    with gzip.open(mysql_dump, "rb") as stream:
        prefix = stream.read(1024 * 1024)
    if not prefix or b"CREATE TABLE" not in prefix:
        raise ResetSafetyError("MySQL logical backup verification failed")

    component_files = [
        path for path in backup_root.rglob("*")
        if path.is_file()
        and path.name not in {"BACKUP_MANIFEST.json", "SHA256SUMS.json"}
    ]
    if mysql_dump not in component_files:
        raise ResetSafetyError("MySQL dump is absent from backup inventory")
    checksums = {
        str(path.relative_to(backup_root)): _sha256(path)
        for path in component_files
    }
    (backup_root / "SHA256SUMS.json").write_text(
        json.dumps(checksums, indent=2, sort_keys=True), encoding="utf-8"
    )
    manifest_path.write_text(json.dumps({
        **base_manifest,
        "verification_status": "VERIFIED",
        "components": {
            "mysql_dump": str(mysql_dump.relative_to(backup_root)),
            "crawler_state": copied["state"],
            "frontier_and_deferred_state": copied["state"],
            "discovery_state": copied["discovery"],
            "run_manifests": copied["manifests"],
        },
    }, indent=2), encoding="utf-8")
    _verify_backup_manifest(backup_root)
    return backup_root


def _reset_mysql(config) -> None:
    with _mysql_connection(config) as connection:
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT DATABASE() AS db, @@read_only AS read_only")
                identity = cursor.fetchone()
                if identity["db"] != EXPECTED_DATABASE or bool(identity["read_only"]):
                    raise ResetSafetyError("Primary identity changed before reset")
                for table in TABLE_DELETE_ORDER:
                    cursor.execute(f"DELETE FROM `{table}`")
            connection.commit()
        except Exception:
            connection.rollback()
            raise


def _reset_filesystem(data_root: Path) -> None:
    for name in FILESYSTEM_TARGETS:
        target = (data_root / name).resolve()
        if target.parent != data_root:
            raise ResetSafetyError("Filesystem reset target escaped data root")
        if target.exists():
            shutil.rmtree(target)


def _verify_clean(data_root: Path, mysql_config) -> None:
    if any(_verify_primary(mysql_config).values()):
        raise ResetSafetyError("Primary is not at zero baseline")
    if any((data_root / name).exists() for name in FILESYSTEM_TARGETS):
        raise ResetSafetyError("Application filesystem reset is incomplete")


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--backup-only", action="store_true")
    mode.add_argument("--confirm-reset-roombeacon", action="store_true")
    parser.add_argument("--trigger-recrawl", action="store_true")
    args = parser.parse_args(argv)
    if args.trigger_recrawl and not args.confirm_reset_roombeacon:
        raise ResetSafetyError("Re-crawl trigger is valid only with confirmed reset")
    return args


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    runtime = get_environment()
    if runtime.mysql_bronze.database != EXPECTED_DATABASE:
        raise ResetSafetyError("Configured database is not RoomBeacon Bronze")
    data_root = _safe_data_root(runtime.crawler.data_dir)
    primary_before = _verify_primary(runtime.mysql_bronze)

    if args.dry_run:
        print(json.dumps({
            "status": "DRY_RUN_READY",
            "primary_verified": True,
            "tables_verified": len(primary_before),
            "backup_required_before_reset": True,
            "replica_dependency": False,
            "minio_dependency": False,
        }, sort_keys=True))
        return 0

    backup_root = _create_and_verify_backup(data_root)
    if args.backup_only:
        print(json.dumps({
            "status": "BACKUP_COMPLETE",
            "backup": str(backup_root),
            "backup_verified": True,
        }, sort_keys=True))
        return 0

    _pause_and_verify_idle()
    _reset_mysql(runtime.mysql_bronze)
    _reset_filesystem(data_root)
    _verify_clean(data_root, runtime.mysql_bronze)

    if args.trigger_recrawl:
        _run(["airflow", "dags", "unpause", "roombeacon_crawler"])
        _run(["airflow", "dags", "trigger", "roombeacon_crawler"])

    print(json.dumps({
        "status": "RESET_COMPLETE",
        "backup": str(backup_root),
        "backup_verified": True,
        "primary_zero": True,
        "recrawl_triggered": bool(args.trigger_recrawl),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
