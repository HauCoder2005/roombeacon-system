import shutil
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from botocore.exceptions import ClientError
import requests

from roombeacon_crawler.application.assets.asset_reconciler import (
    DEFAULT_ASSET_BATCH_SIZE,
    AssetReconcilerService,
)
from roombeacon_crawler.models.asset_item import (
    AssetErrorCategory,
    AssetBatchResult,
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
            resolver=lambda _host, _port: {"93.184.216.34"},
        )
        self.mock_s3 = MagicMock()
        self.reconciler._s3_client = self.mock_s3

    def test_production_asset_batch_default_is_100(self):
        self.assertEqual(DEFAULT_ASSET_BATCH_SIZE, 100)
        self.assertEqual(AssetBatchResult().batch_budget, 100)

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
        mock_resp.iter_content.return_value = [jpeg_bytes]

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
            self.mock_s3.head_object.assert_called_once()
            self.assertTrue(self.state_repo.is_success("phongtro123", "asset_001"))

    def test_html_masquerading_as_image_rejected(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.headers = {"Content-Type": "text/html; charset=utf-8"}
        mock_resp.content = b"<html><head><title>Cloudflare Challenge</title></head></html>"
        mock_resp.iter_content.return_value = [mock_resp.content]

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

    def _result_for(self, source: str) -> AssetBatchResult:
        result = AssetBatchResult()
        result.per_source = {source: SourceAssetMetrics(source=source)}
        return result

    def test_private_url_is_security_rejected(self):
        reconciler = AssetReconcilerService(
            state_repo=self.state_repo,
            bucket_name="test-roombeacon-assets",
            resolver=lambda _host, _port: {"127.0.0.1"},
        )
        item = AssetItem(
            asset_id="private", source="nhatrovn", platform_post_id="1",
            rental_post_id=1, image_url="https://images.example.test/a.jpg",
            position=1, object_key="nhatrovn/1/a.jpg",
        )
        result = self._result_for("nhatrovn")
        with patch("requests.get") as request:
            reconciler._process_single_asset(item, self.mock_s3, result)
        request.assert_not_called()
        self.assertEqual(item.last_error_category, AssetErrorCategory.SECURITY_REJECTED)

    def test_redirect_to_private_ip_is_security_rejected(self):
        redirect = MagicMock(status_code=302, headers={"Location": "http://127.0.0.1/a.jpg"})
        item = AssetItem(
            asset_id="redirect", source="nhatot", platform_post_id="2",
            rental_post_id=2, image_url="https://images.example.test/a.jpg",
            position=1, object_key="nhatot/2/a.jpg",
        )
        result = self._result_for("nhatot")
        with patch("requests.get", return_value=redirect) as request:
            self.reconciler._process_single_asset(item, self.mock_s3, result)
        self.assertEqual(request.call_count, 1)
        self.assertEqual(item.last_error_category, AssetErrorCategory.SECURITY_REJECTED)
        self.mock_s3.put_object.assert_not_called()

    def test_oversized_image_is_rejected_before_upload(self):
        response = MagicMock(
            status_code=200,
            headers={"Content-Type": "image/jpeg", "Content-Length": str(16 * 1024 * 1024)},
        )
        item = AssetItem(
            asset_id="large", source="phongtro123", platform_post_id="3",
            rental_post_id=3, image_url="https://images.example.test/a.jpg",
            position=1, object_key="phongtro123/3/a.jpg",
        )
        result = self._result_for("phongtro123")
        with patch("requests.get", return_value=response):
            self.reconciler._process_single_asset(item, self.mock_s3, result)
        self.assertEqual(item.status, AssetStatus.TERMINAL_FAILURE)
        self.mock_s3.put_object.assert_not_called()

    def test_upload_failure_only_updates_asset_retry_state(self):
        jpeg = b"\xff\xd8\xff" + b"\x00" * 16
        response = MagicMock(status_code=200, headers={"Content-Type": "image/jpeg"})
        response.iter_content.return_value = [jpeg]
        self.mock_s3.put_object.side_effect = RuntimeError("credential-bearing payload")
        item = AssetItem(
            asset_id="upload-fail", source="phongtro123", platform_post_id="4",
            rental_post_id=4, image_url="https://images.example.test/a.jpg",
            position=1, object_key="phongtro123/4/a.jpg",
        )
        result = self._result_for("phongtro123")
        with patch("requests.get", return_value=response), patch.object(
            self.reconciler, "get_mysql_connection"
        ) as mysql:
            self.reconciler._process_single_asset(item, self.mock_s3, result)
        mysql.assert_not_called()
        self.assertEqual(item.status, AssetStatus.RETRYABLE_FAILURE)
        self.assertNotIn("credential-bearing", item.last_error_message)

    def test_minio_existing_object_is_idempotent_skip(self):
        self.mock_s3.head_object.return_value = {"ContentLength": 10}
        self.assertTrue(self.reconciler._object_exists(self.mock_s3, "nhatot/5/a.jpg"))
        self.mock_s3.head_object.assert_called_once_with(
            Bucket="test-roombeacon-assets", Key="nhatot/5/a.jpg"
        )

    def test_minio_client_reuses_provisioned_bucket_without_bucket_admin_calls(self):
        self.reconciler._s3_client = None
        self.reconciler.minio_cfg = SimpleNamespace(
            host="minio", port=9000, access_key="fake", secret_key="fake",
            root_user=None, root_password=None,
        )
        with patch("boto3.client", return_value=self.mock_s3):
            client = self.reconciler.get_s3_client()
        self.assertIs(client, self.mock_s3)
        self.mock_s3.head_bucket.assert_not_called()
        self.mock_s3.create_bucket.assert_not_called()
        self.mock_s3.list_buckets.assert_not_called()

    def test_missing_object_is_not_treated_as_verified(self):
        self.mock_s3.head_object.side_effect = ClientError(
            {"Error": {"Code": "404", "Message": "Not Found"}}, "HeadObject"
        )
        self.assertFalse(self.reconciler._object_exists(self.mock_s3, "nhatot/5/a.jpg"))

    def test_multiple_sources_have_separate_deterministic_paths(self):
        url = "https://images.example.test/shared.jpg"
        first = AssetItem.generate_object_key("nhatrovn", "same", 1, url)
        second = AssetItem.generate_object_key("nhatot", "same", 1, url)
        self.assertNotEqual(first, second)
        self.assertTrue(first.startswith("nhatrovn/"))
        self.assertTrue(second.startswith("nhatot/"))

    def test_duplicate_observation_rows_yield_one_candidate(self):
        row = {
            "image_id": 1, "rental_post_id": 7,
            "image_url": "https://images.example.test/one.jpg", "position": 1,
            "platform_post_id": "listing-7", "source": "nhatrovn",
        }
        cursor = MagicMock()
        cursor.fetchall.return_value = [row, dict(row, image_id=2)]
        cursor.__enter__.return_value = cursor
        connection = MagicMock()
        connection.__enter__.return_value = connection
        connection.cursor.return_value = cursor
        with patch.object(self.reconciler, "get_mysql_connection", return_value=connection):
            candidates = self.reconciler.discover_actionable_candidates_per_source(["nhatrovn"])
        self.assertEqual(len(candidates["nhatrovn"]), 1)

    def test_success_state_across_runs_skips_verified_object(self):
        url = "https://images.example.test/one.jpg"
        asset_id = AssetItem.generate_asset_id("nhatrovn", "listing-8", url)
        item = AssetItem(
            asset_id=asset_id, source="nhatrovn", platform_post_id="listing-8",
            rental_post_id=8, image_url=url, position=1,
            object_key=AssetItem.generate_object_key("nhatrovn", "listing-8", 1, url),
            status=AssetStatus.SUCCESS,
        )
        self.state_repo.save_asset(item)
        row = {
            "image_id": 1, "rental_post_id": 8, "image_url": url, "position": 1,
            "platform_post_id": "listing-8", "source": "nhatrovn",
        }
        cursor = MagicMock()
        cursor.fetchall.return_value = [row]
        cursor.__enter__.return_value = cursor
        connection = MagicMock()
        connection.__enter__.return_value = connection
        connection.cursor.return_value = cursor
        self.mock_s3.head_object.return_value = {"ContentLength": 10}
        with patch.object(self.reconciler, "get_mysql_connection", return_value=connection):
            candidates = self.reconciler.discover_actionable_candidates_per_source(
                ["nhatrovn"], s3=self.mock_s3
            )
        self.assertEqual(candidates["nhatrovn"], [])
        self.assertEqual(self.reconciler._last_already_stored_by_source["nhatrovn"], 1)

    def test_selected_outcomes_are_mutually_exclusive(self):
        jpeg = b"\xff\xd8\xff" + b"\x00" * 16
        valid_response = MagicMock(status_code=200, headers={"Content-Type": "image/jpeg"})
        valid_response.iter_content.return_value = [jpeg]
        invalid_response = MagicMock(status_code=200, headers={"Content-Type": "image/svg+xml"})
        invalid_response.iter_content.return_value = [b"<svg></svg>"]
        result = AssetBatchResult(batch_budget=3, batch_used=3, attempted=3)
        result.per_source = {"nhatrovn": SourceAssetMetrics(source="nhatrovn")}

        items = [
            AssetItem(
                asset_id=f"outcome-{index}", source="nhatrovn",
                platform_post_id=str(index), rental_post_id=index,
                image_url=f"https://images.example.test/{index}.jpg",
                position=1, object_key=f"nhatrovn/{index}/image.jpg",
            )
            for index in range(3)
        ]
        self.mock_s3.head_object.return_value = {"ContentLength": len(jpeg)}
        with patch.object(
            self.reconciler,
            "_request_public_asset",
            side_effect=[valid_response, invalid_response, requests.exceptions.Timeout()],
        ):
            for item in items:
                self.reconciler._process_single_asset(item, self.mock_s3, result)

        self.assertEqual(result.downloaded, 1)
        self.assertEqual(result.uploaded, 1)
        self.assertEqual(result.post_upload_verified, 1)
        self.assertEqual(result.invalid_magic, 1)
        self.assertEqual(result.terminal_failed, 1)
        self.assertEqual(result.retryable_failed, 1)
        self.assertEqual(
            result.batch_used,
            result.post_upload_verified + result.terminal_failed + result.retryable_failed,
        )


if __name__ == "__main__":
    unittest.main()
