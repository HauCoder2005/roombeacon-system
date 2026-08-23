import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
import requests

from roombeacon_crawler.application.assets.asset_reconciler import (
    AssetReconcilerService,
)
from roombeacon_crawler.models.asset_item import (
    AssetErrorCategory,
    AssetItem,
    AssetStatus,
    SourceAssetMetrics,
)
from roombeacon_crawler.policies.fair_asset_scheduler import FairAssetScheduler
from roombeacon_crawler.repositories.local_asset_state_repository import (
    LocalAssetStateRepository,
)


class TestFairAssetScheduler(unittest.TestCase):

    def test_scenario_a_all_sources_progress(self):
        candidates = {
            "nhatrovn": [f"nv_{i}" for i in range(10000)],
            "phongtro123": [f"pt_{i}" for i in range(100)],
            "nhatot": [f"nt_{i}" for i in range(100)],
            "batdongsan": [f"bds_{i}" for i in range(10)],
        }
        batch = FairAssetScheduler.allocate_fair_batch(candidates, batch_size=50)
        self.assertEqual(len(batch), 50)

        counts = {
            "batdongsan": sum(1 for x in batch if x.startswith("bds_")),
            "phongtro123": sum(1 for x in batch if x.startswith("pt_")),
            "nhatot": sum(1 for x in batch if x.startswith("nt_")),
            "nhatrovn": sum(1 for x in batch if x.startswith("nv_")),
        }
        self.assertEqual(counts["batdongsan"], 10)  # Lấy hết 10 item của bds
        self.assertGreaterEqual(counts["phongtro123"], 12)
        self.assertGreaterEqual(counts["nhatot"], 12)
        self.assertGreaterEqual(counts["nhatrovn"], 12)

    def test_scenario_b_zero_asset_source_spillover(self):
        candidates = {
            "phongtro123": [f"pt_{i}" for i in range(50)],
            "nhatrovn": [f"nv_{i}" for i in range(50)],
            "nhatot": [f"nt_{i}" for i in range(50)],
            "batdongsan": [],
        }
        batch = FairAssetScheduler.allocate_fair_batch(candidates, batch_size=30)
        self.assertEqual(len(batch), 30)
        counts = {
            "batdongsan": sum(1 for x in batch if x.startswith("bds_")),
            "phongtro123": sum(1 for x in batch if x.startswith("pt_")),
            "nhatot": sum(1 for x in batch if x.startswith("nt_")),
            "nhatrovn": sum(1 for x in batch if x.startswith("nv_")),
        }
        self.assertEqual(counts["batdongsan"], 0)
        self.assertEqual(counts["phongtro123"], 10)
        self.assertEqual(counts["nhatrovn"], 10)
        self.assertEqual(counts["nhatot"], 10)

    def test_scenario_c_single_active_source_consumes_full_batch(self):
        candidates = {
            "phongtro123": [],
            "nhatrovn": [f"nv_{i}" for i in range(100)],
            "nhatot": [],
            "batdongsan": [],
        }
        batch = FairAssetScheduler.allocate_fair_batch(candidates, batch_size=50)
        self.assertEqual(len(batch), 50)
        self.assertTrue(all(item.startswith("nv_") for item in batch))

    def test_scenario_d_low_volume_source_two_items_spillover(self):
        candidates = {
            "batdongsan": ["bds_1", "bds_2"],
            "phongtro123": [f"pt_{i}" for i in range(100)],
        }
        batch = FairAssetScheduler.allocate_fair_batch(candidates, batch_size=20)
        self.assertEqual(len(batch), 20)
        bds_count = sum(1 for item in batch if item.startswith("bds_"))
        pt_count = sum(1 for item in batch if item.startswith("pt_"))
        self.assertEqual(bds_count, 2)
        self.assertEqual(pt_count, 18)

    def test_scenario_e_nhatrovn_id_stream_does_not_starve_older_sources(self):
        # Giả lập nhiều lần chạy liên tiếp, các nguồn nhỏ hơn vẫn được xử lý đều
        candidates = {
            "nhatrovn": [f"nv_{i}" for i in range(1000)],
            "phongtro123": [f"pt_{i}" for i in range(30)],
        }
        batch_1 = FairAssetScheduler.allocate_fair_batch(candidates, batch_size=20)
        pt_in_b1 = [x for x in batch_1 if x.startswith("pt_")]
        self.assertEqual(len(pt_in_b1), 10)  # Lấy đều 10 pt và 10 nv


class TestAssetReconciler(unittest.TestCase):

    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp())
        self.state_repo = LocalAssetStateRepository(base_dir=self.test_dir)
        self.reconciler = AssetReconcilerService(
            state_repo=self.state_repo,
            bucket_name="test-roombeacon-assets",
        )
        self.mock_s3 = MagicMock()
        self.reconciler._s3_client = self.mock_s3

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_deterministic_object_key(self):
        key1 = AssetItem.generate_object_key("nhatot", "12345", 1, "https://cdn.example.com/img1.jpg", ext="jpg")
        key2 = AssetItem.generate_object_key("nhatot", "12345", 1, "https://cdn.example.com/img1.jpg", ext="jpg")
        self.assertEqual(key1, key2)
        self.assertTrue(key1.startswith("nhatot/12345/img_1_"))
        self.assertTrue(key1.endswith(".jpg"))

    def test_valid_image_accepted_and_uploaded(self):
        jpeg_bytes = b"\xff\xd8\xff\xe0\x00\x10JFIF" + b"\x00" * 50

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.headers = {"Content-Type": "image/jpeg"}
        mock_resp.content = jpeg_bytes

        with patch("requests.get", return_value=mock_resp):
            item = AssetItem(
                asset_id="asset_001",
                source="phongtro123",
                platform_post_id="pt_555",
                rental_post_id=555,
                image_url="https://phongtro123.com/images/room1.jpg",
                position=1,
                object_key="phongtro123/pt_555/img_1.jpg",
            )
            res = MagicMock()
            res.downloaded = 0
            res.uploaded = 0
            res.terminal_failed = 0
            res.retryable_failed = 0
            res.per_source = {"phongtro123": SourceAssetMetrics(source="phongtro123")}

            self.reconciler._process_single_asset(item, self.mock_s3, res)

            self.assertEqual(item.status, AssetStatus.SUCCESS)
            self.assertEqual(item.content_type, "image/jpeg")
            self.assertEqual(res.uploaded, 1)
            self.mock_s3.put_object.assert_called_once()
            self.assertTrue(self.state_repo.is_success("phongtro123", "asset_001"))

    def test_html_masquerading_as_image_rejected(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.headers = {"Content-Type": "text/html; charset=utf-8"}
        mock_resp.content = b"<html><head><title>Cloudflare Challenge</title></head></html>"

        with patch("requests.get", return_value=mock_resp):
            item = AssetItem(
                asset_id="asset_html",
                source="batdongsan",
                platform_post_id="bds_11",
                rental_post_id=11,
                image_url="https://batdongsan.com/blocked_image.jpg",
                position=1,
                object_key="batdongsan/bds_11/img_1.jpg",
            )
            res = MagicMock()
            res.terminal_failed = 0
            res.uploaded = 0
            res.per_source = {"batdongsan": SourceAssetMetrics(source="batdongsan")}

            self.reconciler._process_single_asset(item, self.mock_s3, res)

            self.assertEqual(item.status, AssetStatus.TERMINAL_FAILURE)
            self.assertEqual(item.last_error_category, AssetErrorCategory.HTML_CHALLENGE)
            self.mock_s3.put_object.assert_not_called()
            self.assertTrue(self.state_repo.is_terminal_failure("batdongsan", "asset_html"))

    def test_timeout_becomes_retryable(self):
        with patch("requests.get", side_effect=requests.exceptions.Timeout("Connection timeout")):
            item = AssetItem(
                asset_id="asset_timeout",
                source="nhatot",
                platform_post_id="nt_99",
                rental_post_id=99,
                image_url="https://cdn.chotot.com/timeout.jpg",
                position=1,
                object_key="nhatot/nt_99/img_1.jpg",
            )
            res = MagicMock()
            res.retryable_failed = 0
            res.uploaded = 0
            res.per_source = {"nhatot": SourceAssetMetrics(source="nhatot")}

            self.reconciler._process_single_asset(item, self.mock_s3, res)

            self.assertEqual(item.status, AssetStatus.RETRYABLE_FAILURE)
            self.assertEqual(item.last_error_category, AssetErrorCategory.TIMEOUT)
            self.assertEqual(res.retryable_failed, 1)
            self.mock_s3.put_object.assert_not_called()

    def test_data_url_marked_terminal_and_not_requested(self):
        item = AssetItem(
            asset_id="asset_data_uri",
            source="nhatot",
            platform_post_id="nt_placeholder",
            rental_post_id=12,
            image_url="data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7",
            position=1,
            object_key="nhatot/nt_placeholder/img_1.gif",
        )
        res = MagicMock()
        res.terminal_failed = 0
        res.per_source = {"nhatot": SourceAssetMetrics(source="nhatot")}

        with patch("requests.get") as mock_get:
            self.reconciler._process_single_asset(item, self.mock_s3, res)
            mock_get.assert_not_called()

        self.assertEqual(item.status, AssetStatus.TERMINAL_FAILURE)
        self.assertEqual(item.last_error_category, AssetErrorCategory.INVALID_DATA_URL)
        self.assertTrue(self.state_repo.is_terminal_failure("nhatot", "asset_data_uri"))


if __name__ == "__main__":
    unittest.main()
