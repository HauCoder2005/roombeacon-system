from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from roombeacon_crawler.enums.crawl_status import CrawlStatus
from roombeacon_crawler.infrastructure.storage.local.local_storage_writer import (
    LocalStorageWriter,
)
from roombeacon_crawler.models.crawl_run_result import CrawlRunResult
from roombeacon_crawler.models.rental_bronze_record import RentalBronzeRecord


class TestLocalStorageWriter(unittest.TestCase):
    def setUp(self) -> None:
        self.test_dir = tempfile.mkdtemp()
        self.writer = LocalStorageWriter(base_data_dir=self.test_dir)

    def tearDown(self) -> None:
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_save_manifest_always_writes_manifest_file_with_valid_path(self) -> None:
        result = CrawlRunResult(
            run_id="run_manifest_test",
            source="test_source",
            target_url="https://test.com/rentals",
            started_at="2026-08-19T00:00:00Z",
            finished_at="2026-08-19T00:00:01Z",
            status=CrawlStatus.ROBOTS_DENIED,
            stop_reason=CrawlStatus.ROBOTS_DENIED,
            records_created=0,
        )

        manifest_file = self.writer.save_manifest(result)
        self.assertTrue(os.path.isfile(manifest_file))
        self.assertEqual(result.manifest_path, manifest_file)
        self.assertIsNone(result.bronze_path)

        with open(manifest_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        self.assertEqual(data["run_id"], "run_manifest_test")
        self.assertEqual(data["source"], "test_source")
        self.assertEqual(data["status"], "robots_denied")
        self.assertEqual(data["records_created"], 0)
        # Manifest JSON file itself must contain non-null manifest_path
        self.assertEqual(data["manifest_path"], manifest_file)
        self.assertIsNone(data["bronze_path"])

    def test_save_manifest_contains_bronze_path_when_records_exist(self) -> None:
        result = CrawlRunResult(
            run_id="run_success_test",
            source="phongtro123",
            target_url="https://phongtro123.com/tinh-thanh/ho-chi-minh",
            started_at="2026-08-19T00:00:00Z",
            finished_at="2026-08-19T00:00:02Z",
            status=CrawlStatus.SUCCESS,
            records_created=10,
            bronze_path=os.path.join(self.test_dir, "bronze", "phongtro123", "2026-08-19", "run_success_test"),
        )

        manifest_file = self.writer.save_manifest(result)
        self.assertEqual(result.manifest_path, manifest_file)

        with open(manifest_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        self.assertEqual(data["manifest_path"], manifest_file)
        self.assertEqual(data["bronze_path"], result.bronze_path)
        self.assertEqual(data["records_created"], 10)

    def test_save_bronze_dataset_with_zero_records_creates_nothing(self) -> None:
        bronze_dir = self.writer.save_bronze_dataset(
            run_id="run_empty_bronze",
            source="nhatot",
            records=[],
            metadata=[],
        )

        self.assertIsNone(bronze_dir)
        bronze_base = os.path.join(self.test_dir, "bronze")
        self.assertFalse(os.path.exists(bronze_base))

    def test_save_bronze_dataset_with_valid_records_creates_files(self) -> None:
        dummy_record = RentalBronzeRecord(
            listing_id="702593",
            source="phongtro123",
            url="https://phongtro123.com/post-702593.html",
            title_raw="Phòng trọ đẹp",
            price_raw="3.5 triệu/tháng",
            area_raw="25 m2",
            address_raw="Quận 10",
            location_raw="Quận 10, TP.HCM",
            description_raw="Phòng trọ sạch sẽ",
            posted_at_raw="Hôm nay",
            crawl_run_id="run_valid_bronze",
            crawled_at=datetime.now(timezone.utc).isoformat(),
        )

        bronze_dir = self.writer.save_bronze_dataset(
            run_id="run_valid_bronze",
            source="phongtro123",
            records=[dummy_record],
            metadata=[],
        )

        self.assertIsNotNone(bronze_dir)
        self.assertTrue(os.path.isdir(bronze_dir))
        listings_file = os.path.join(bronze_dir, "listings.json")
        self.assertTrue(os.path.isfile(listings_file))

        with open(listings_file, "r", encoding="utf-8") as f:
            records_data = json.load(f)

        self.assertEqual(len(records_data), 1)
        self.assertEqual(records_data[0]["listing_id"], "702593")

    def test_working_directory_independence(self) -> None:
        orig_cwd = os.getcwd()
        unrelated_cwd = tempfile.mkdtemp()
        target_data_dir = tempfile.mkdtemp()

        try:
            os.chdir(unrelated_cwd)
            isolated_writer = LocalStorageWriter(base_data_dir=target_data_dir)

            dummy_record = RentalBronzeRecord(
                listing_id="88888",
                source="nhatot",
                url="https://www.nhatot.com/88888.htm",
                title_raw="Test CWD Independence",
                price_raw="4 tr/tháng",
                area_raw="30 m2",
                address_raw="Quận 1",
                location_raw="Quận 1, TP.HCM",
                description_raw="Test description",
                posted_at_raw="Vừa xong",
                crawl_run_id="run_cwd_test",
            )

            bronze_dir = isolated_writer.save_bronze_dataset(
                run_id="run_cwd_test",
                source="nhatot",
                records=[dummy_record],
                metadata=[],
            )

            self.assertIsNotNone(bronze_dir)
            self.assertTrue(bronze_dir.startswith(str(Path(target_data_dir).resolve())))
            # Verify no data folder created under current working directory
            self.assertFalse(os.path.exists(os.path.join(unrelated_cwd, "data")))
        finally:
            os.chdir(orig_cwd)
            shutil.rmtree(unrelated_cwd, ignore_errors=True)
            shutil.rmtree(target_data_dir, ignore_errors=True)

    def test_save_manifest_failure_preserves_error(self) -> None:
        result = CrawlRunResult(
            run_id="run_fail_test",
            source="test_source",
            target_url="https://test.com",
            started_at="2026-08-19T00:00:00Z",
            finished_at="2026-08-19T00:00:01Z",
        )

        with patch("builtins.open", side_effect=IOError("Disk full")):
            with self.assertRaises(IOError):
                self.writer.save_manifest(result)

        self.assertIsNone(result.manifest_path)


if __name__ == "__main__":
    unittest.main()
