import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from sqlalchemy import create_engine, text

from roombeacon_crawler.application.persistence.persist_observations import PersistBronzeObservationsUseCase
from roombeacon_crawler.application.reconciliation.discovery import BronzeRunDiscoveryService, BronzeRunInfo
from roombeacon_crawler.application.reconciliation.reconciler import BronzeReconcilerService
from roombeacon_crawler.domain.models.bronze_observation import BronzeObservation
from roombeacon_crawler.infrastructure.mysql.repositories.observation_repository import MySQLObservationRepository
from roombeacon_crawler.infrastructure.mysql.repositories.platform_repository import MySQLPlatformRepository
from roombeacon_crawler.infrastructure.mysql.repositories.post_children_repository import MySQLPostChildrenRepository
from roombeacon_crawler.infrastructure.mysql.repositories.rental_post_repository import MySQLRentalPostRepository
from roombeacon_crawler.infrastructure.mysql.transaction import MySQLTransactionManager


class TestBronzeReconciliation(unittest.TestCase):
    """Bộ kiểm thử đơn vị và tích hợp cho quy trình Bronze Reconciliation."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.bronze_root = Path(self.temp_dir) / "bronze"
        self.bronze_root.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_bronze_run_discovery_valid(self):
        """1. Kiểm thử quét và phát hiện các Bronze run hợp lệ."""
        run_dir = self.bronze_root / "phongtro123" / "2026-08-21" / "run_20260821_120000"
        run_dir.mkdir(parents=True, exist_ok=True)
        listings = [{"listing_id": "1001", "source": "phongtro123", "title": "Phòng đẹp"}]
        with open(run_dir / "listings.json", "w", encoding="utf-8") as f:
            json.dump(listings, f)

        runs = BronzeRunDiscoveryService.discover_bronze_runs(self.bronze_root)
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0].source, "phongtro123")
        self.assertEqual(runs[0].run_id, "run_20260821_120000")
        self.assertEqual(runs[0].record_count, 1)

    def test_invalid_and_corrupt_directory_ignored(self):
        """2 & 3. Thư mục không hợp lệ hoặc JSON bị lỗi không làm sập discovery."""
        valid_dir = self.bronze_root / "nhatot" / "2026-08-21" / "run_valid"
        valid_dir.mkdir(parents=True, exist_ok=True)
        with open(valid_dir / "listings.json", "w", encoding="utf-8") as f:
            json.dump([{"listing_id": "2001"}], f)

        # Thư mục thiếu listings.json
        empty_dir = self.bronze_root / "nhatot" / "2026-08-21" / "run_empty"
        empty_dir.mkdir(parents=True, exist_ok=True)

        # Thư mục có listings.json bị hỏng
        corrupt_dir = self.bronze_root / "nhatot" / "2026-08-21" / "run_corrupt"
        corrupt_dir.mkdir(parents=True, exist_ok=True)
        with open(corrupt_dir / "listings.json", "w", encoding="utf-8") as f:
            f.write("{invalid_json_corrupt_content")

        runs = BronzeRunDiscoveryService.discover_bronze_runs(self.bronze_root)
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0].run_id, "run_valid")

    def test_batch_size_respected(self):
        """Kiểm thử giới hạn batch_limit được tuân thủ chính xác."""
        runs = [
            BronzeRunInfo(
                source="phongtro123",
                date="2026-08-21",
                run_id=f"run_{i}",
                run_path=f"/fake/path_{i}",
                listings_path=f"/fake/path_{i}/listings.json",
                record_count=10,
            )
            for i in range(30)
        ]

        with patch.object(BronzeReconcilerService, "get_persisted_run_counts", return_value={}):
            batch, total_missing, already_complete = BronzeReconcilerService.identify_missing_runs(
                discovered_runs=runs,
                batch_limit=10,
            )
            self.assertEqual(len(batch), 10)
            self.assertEqual(total_missing, 30)
            self.assertEqual(already_complete, 0)

    def test_idempotent_reconciliation_mock_usecase(self):
        """Kiểm thử quy trình reconcile_single_run gọi Clean Architecture use case."""
        run_dir = self.bronze_root / "phongtro123" / "2026-08-21" / "run_test_import"
        run_dir.mkdir(parents=True, exist_ok=True)
        listings = [
            {"listing_id": "3001", "source": "phongtro123", "title": "Nhà trọ A", "url": "https://p.com/1"},
            {"listing_id": "3002", "source": "phongtro123", "title": "Nhà trọ B", "url": "https://p.com/2"},
        ]
        with open(run_dir / "listings.json", "w", encoding="utf-8") as f:
            json.dump(listings, f)

        run_info = BronzeRunInfo(
            source="phongtro123",
            date="2026-08-21",
            run_id="run_test_import",
            run_path=str(run_dir),
            listings_path=str(run_dir / "listings.json"),
            record_count=2,
        )

        with patch("roombeacon_crawler.application.reconciliation.reconciler.PersistBronzeObservationsUseCase") as mock_uc_cls:
            mock_uc = MagicMock()
            mock_res = MagicMock(
                observations_inserted=2,
                technical_duplicates=0,
                posts_created=2,
                posts_existing=0,
            )
            mock_uc.execute.return_value = mock_res
            mock_uc_cls.return_value = mock_uc

            fake_engine = create_engine("sqlite:///:memory:")
            result = BronzeReconcilerService.reconcile_single_run(run_info, engine=fake_engine)
            self.assertEqual(result["status"], "SUCCESS")
            self.assertEqual(result["observations_inserted"], 2)
            self.assertEqual(result["observations_scanned"], 2)
            mock_uc.execute.assert_called_once()

    def test_checkpoint_save_and_load(self):
        """Kiểm thử lưu và đọc checkpoint bền vững."""
        ckpt_path = Path(self.temp_dir) / "state" / "bronze_reconciler.json"
        state = {"runs_discovered": 100, "remaining_backlog": 10}
        BronzeReconcilerService.save_checkpoint(state, ckpt_path)

        loaded = BronzeReconcilerService.load_checkpoint(ckpt_path)
        self.assertEqual(loaded["runs_discovered"], 100)
        self.assertEqual(loaded["remaining_backlog"], 10)
        self.assertIn("updated_at", loaded)

    def test_persistence_failure_leaves_bronze_intact(self):
        """Kiểm thử khi nạp MySQL thất bại, file Bronze trên đĩa vẫn nguyên vẹn 100%."""
        run_dir = self.bronze_root / "phongtro123" / "2026-08-21" / "run_failure_test"
        run_dir.mkdir(parents=True, exist_ok=True)
        listings_file = run_dir / "listings.json"
        with open(listings_file, "w", encoding="utf-8") as f:
            json.dump([{"listing_id": "4001", "source": "phongtro123"}], f)

        run_info = BronzeRunInfo(
            source="phongtro123",
            date="2026-08-21",
            run_id="run_failure_test",
            run_path=str(run_dir),
            listings_path=str(listings_file),
            record_count=1,
        )

        fake_engine = create_engine("sqlite:///:memory:")
        with patch("roombeacon_crawler.application.reconciliation.reconciler.PersistBronzeObservationsUseCase") as mock_uc_cls:
            mock_uc = MagicMock()
            mock_uc.execute.side_effect = RuntimeError("Database connection lost")
            mock_uc_cls.return_value = mock_uc

            with self.assertRaises(RuntimeError):
                BronzeReconcilerService.reconcile_single_run(run_info, engine=fake_engine)

        # File Bronze vẫn tồn tại nguyên vẹn
        self.assertTrue(listings_file.exists())
        with open(listings_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(len(data), 1)

    def test_audit_and_identify_missing_runs_metrics(self):
        """Kiểm thử phân loại chính xác: already_reconciled, partially_missing, fully_missing."""
        runs = [
            BronzeRunInfo("s1", "2026-08-21", "run_complete", "/p1", "/p1/l.json", record_count=10),
            BronzeRunInfo("s1", "2026-08-21", "run_partial", "/p2", "/p2/l.json", record_count=10),
            BronzeRunInfo("s1", "2026-08-21", "run_missing", "/p3", "/p3/l.json", record_count=10),
        ]

        persisted_mock = {
            "run_complete": 10,  # Đủ
            "run_partial": 4,    # Thiếu 6
            # run_missing: 0
        }

        batch, meta = BronzeReconcilerService.audit_and_identify_missing_runs(
            discovered_runs=runs,
            batch_limit=25,
            persisted_counts=persisted_mock,
        )

        self.assertEqual(meta["runs_discovered"], 3)
        self.assertEqual(meta["already_reconciled"], 1)
        self.assertEqual(meta["partially_missing"], 1)
        self.assertEqual(meta["fully_missing"], 1)
        self.assertEqual(meta["not_inspected_yet"], 0)
        self.assertEqual(meta["total_real_backlog"], 2)
        self.assertEqual(len(batch), 2)
        # Invariant
        self.assertEqual(
            meta["runs_discovered"],
            meta["already_reconciled"] + meta["partially_missing"] + meta["fully_missing"] + meta["not_inspected_yet"],
        )

    def test_duckdb_analytics_pool_assigned(self):
        """Kiểm thử pool='duckdb_analytics_pool' được gán cho task refresh trong cả 2 DAG."""
        from airflow.dags.crawler.roombeacon_crawler import roombeacon_crawler
        from airflow.dags.reconciliation.roombeacon_bronze_reconciler import roombeacon_bronze_reconciler

        crawler_dag = roombeacon_crawler()
        reconciler_dag = roombeacon_bronze_reconciler()

        t_crawler = crawler_dag.get_task("refresh_duckdb_analytics")
        t_reconciler = reconciler_dag.get_task("refresh_duckdb_analytics")

        self.assertEqual(t_crawler.pool, "duckdb_analytics_pool")
        self.assertEqual(t_reconciler.pool, "duckdb_analytics_pool")


if __name__ == "__main__":
    unittest.main()
