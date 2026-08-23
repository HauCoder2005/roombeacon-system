import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock

from roombeacon_crawler.application.persistence.persist_observations import (
    BronzeImportResult,
    PersistBronzeObservationsUseCase,
)
from roombeacon_crawler.domain.errors.domain_error import PersistenceError
from roombeacon_crawler.domain.models.bronze_observation import BronzeObservation
from roombeacon_crawler.domain.ports.persistence_port import (
    ObservationRepositoryPort,
    PlatformRepositoryPort,
    PostChildrenRepositoryPort,
    RentalPostRepositoryPort,
    TransactionManagerPort,
)
from roombeacon_crawler.mappers.bronze_observation_loader import (
    BronzeObservationLoader,
    compute_observation_content_hash,
)


class TestBronzeObservationLoaderAndHash(unittest.TestCase):
    """Kiểm thử tính toán hash và nạp BronzeObservation từ file artifact."""

    def test_deterministic_content_hash(self):
        hash1 = compute_observation_content_hash(
            title_raw="Phòng trọ Q1",
            price_raw="3.5 triệu/tháng",
            area_raw="25 m2",
            image_urls=["http://img2.jpg", "http://img1.jpg"],
        )
        hash2 = compute_observation_content_hash(
            title_raw="Phòng trọ Q1",
            price_raw="3.5 triệu/tháng",
            area_raw="25 m2",
            image_urls=["http://img1.jpg", "http://img2.jpg"],  # Khác thứ tự đầu vào
        )
        self.assertEqual(hash1, hash2, "Content hash phải tất định dù thứ tự list thay đổi.")

    def test_loader_merges_listing_and_detail(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            listings_data = [
                {
                    "source": "nhatot",
                    "listing_id": "1001",
                    "url": "https://nhatot.com/1001",
                    "title_raw": "Phòng trọ đẹp",
                    "price_raw": "3 triệu",
                    "area_raw": "20m2",
                    "location_raw": "Quận 10",
                }
            ]
            details_data = [
                {
                    "source_listing_id": "1001",
                    "description_raw": "Đầy đủ tiện nghi máy lạnh",
                    "address_raw": "123 Đường 3/2",
                    "amenities_raw": ["Wifi", "Máy lạnh"],
                    "image_urls_raw": ["http://img1.jpg"],
                }
            ]
            with open(tmp_path / "listings.json", "w", encoding="utf-8") as f:
                json.dump(listings_data, f)
            with open(tmp_path / "details.json", "w", encoding="utf-8") as f:
                json.dump(details_data, f)

            observations = BronzeObservationLoader.load_from_bronze_dir(tmp_path, run_id="run_test_01")
            self.assertEqual(len(observations), 1)
            obs = observations[0]
            self.assertEqual(obs.listing_id, "1001")
            self.assertEqual(obs.run_id, "run_test_01")
            self.assertEqual(obs.title_raw, "Phòng trọ đẹp")
            self.assertEqual(obs.description_raw, "Đầy đủ tiện nghi máy lạnh")
            self.assertEqual(obs.address_raw, "123 Đường 3/2")
            self.assertEqual(obs.amenities_raw, ["Wifi", "Máy lạnh"])
            self.assertIn("content_hash", obs.attributes)


class TestPersistBronzeObservationsUseCase(unittest.TestCase):
    """Kiểm thử Unit of Work, Transaction Commit/Rollback và tính lũy đẳng."""

    def setUp(self):
        self.mock_platform_repo = MagicMock(spec=PlatformRepositoryPort)
        self.mock_platform_repo.get_or_create_platform.return_value = 1

        self.mock_post_repo = MagicMock(spec=RentalPostRepositoryPort)
        self.mock_post_repo.upsert_post.return_value = (10, True)

        self.mock_obs_repo = MagicMock(spec=ObservationRepositoryPort)
        self.mock_obs_repo.insert_observation.return_value = (100, True)

        self.mock_children_repo = MagicMock(spec=PostChildrenRepositoryPort)
        self.mock_tx_mgr = MagicMock(spec=TransactionManagerPort)

        self.use_case = PersistBronzeObservationsUseCase(
            platform_repo=self.mock_platform_repo,
            rental_post_repo=self.mock_post_repo,
            observation_repo=self.mock_obs_repo,
            children_repo=self.mock_children_repo,
            transaction_mgr=self.mock_tx_mgr,
        )

    def test_successful_commit_transaction(self):
        obs = BronzeObservation(
            source="nhatot",
            listing_id="1001",
            run_id="run_01",
            url="https://nhatot.com/1001",
            title_raw="Phòng trọ",
        )
        result = self.use_case.execute([obs])

        self.mock_tx_mgr.begin.assert_called_once()
        self.mock_platform_repo.get_or_create_platform.assert_called_once()
        self.mock_post_repo.upsert_post.assert_called_once()
        self.mock_obs_repo.insert_observation.assert_called_once()
        self.mock_children_repo.persist_children.assert_called_once()
        self.mock_tx_mgr.commit.assert_called_once()
        self.mock_tx_mgr.rollback.assert_not_called()

        self.assertEqual(result.total_observations, 1)
        self.assertEqual(result.posts_created, 1)
        self.assertEqual(result.observations_inserted, 1)
        self.assertEqual(result.technical_duplicates, 0)

    def test_rollback_on_failure(self):
        self.mock_children_repo.persist_children.side_effect = Exception("DB Connection Lost")

        obs = BronzeObservation(
            source="nhatot",
            listing_id="1001",
            run_id="run_01",
            url="https://nhatot.com/1001",
            title_raw="Phòng trọ",
        )

        with self.assertRaises(PersistenceError):
            self.use_case.execute([obs])

        self.mock_tx_mgr.begin.assert_called_once()
        self.mock_tx_mgr.rollback.assert_called_once()
        self.mock_tx_mgr.commit.assert_not_called()

    def test_same_run_technical_idempotency(self):
        # Giả lập lần import thứ 2 của cùng một run_id: observation đã tồn tại
        self.mock_post_repo.upsert_post.return_value = (10, False)
        self.mock_obs_repo.insert_observation.return_value = (100, False)  # is_inserted = False

        obs = BronzeObservation(
            source="nhatot",
            listing_id="1001",
            run_id="run_01",
            url="https://nhatot.com/1001",
            title_raw="Phòng trọ",
        )

        result = self.use_case.execute([obs])

        self.assertEqual(result.posts_created, 0)
        self.assertEqual(result.posts_existing, 1)
        self.assertEqual(result.observations_inserted, 0)
        self.assertEqual(result.technical_duplicates, 1)
        # Khi là technical duplicate, không insert lại child rows
        self.mock_children_repo.persist_children.assert_not_called()
        self.mock_tx_mgr.commit.assert_called_once()

    def test_platform_post_id_long_capacity(self):
        """Kiểm thử platform_post_id dài > 191 ký tự (lên tới 512 ký tự) được truyền nguyên vẹn không bị cắt ngắn."""
        long_id = "tinh-thanh/ho-chi-minh/cho-thue-phong-tro-cao-cap-nhu-khach-san-gia-re-ngay-kha-van-can-thu-duc-lh0939073433-" + "a" * 150
        self.assertGreater(len(long_id), 191)
        self.assertLessEqual(len(long_id), 512)

        obs = BronzeObservation(
            source="phongtro123",
            listing_id=long_id,
            run_id="run_long_01",
            url=f"https://phongtro123.com/{long_id}.html",
            title_raw="Phòng trọ dài ID",
        )
        self.use_case.execute([obs])

        # Kiểm tra upsert_post nhận đúng long_id không bị truncate
        self.mock_post_repo.upsert_post.assert_called_once()
        passed_obs = self.mock_post_repo.upsert_post.call_args[0][0]
        self.assertEqual(passed_obs.listing_id, long_id)
        self.assertEqual(len(passed_obs.listing_id), len(long_id))


class TestPostAddressesAndSchemaMapping(unittest.TestCase):
    """Kiểm thử MySQLPostChildrenRepository map đúng vào post_addresses và post_details."""

    def test_post_addresses_mapping_without_post_locations(self):
        from roombeacon_crawler.infrastructure.mysql.repositories.post_children_repository import MySQLPostChildrenRepository

        mock_conn = MagicMock()
        repo = MySQLPostChildrenRepository(connection=mock_conn)

        obs = BronzeObservation(
            source="phongtro123",
            listing_id="700123",
            run_id="run_01",
            url="https://phongtro123.com/700123.html",
            title_raw="Phòng trọ Tân Bình",
            price_raw="4.5 triệu/tháng",
            area_raw="30 m2",
            location_raw="Quận Tân Bình, TP.HCM",
            address_raw="123 Lê Văn Sỹ, Phường 1, Tân Bình",
            seller_name_raw="Nguyễn Văn A",
            seller_phone_raw="0901234567",
        )

        repo.persist_children(observation=obs, post_id=1, observation_id=10)

        # Lấy danh sách các câu lệnh SQL đã execute
        executed_sqls = [str(call[0][0]) for call in mock_conn.execute.call_args_list]

        # Xác nhận có INSERT vào post_addresses và post_details
        has_post_addresses = any("INSERT INTO post_addresses" in sql for sql in executed_sqls)
        has_post_details = any("INSERT INTO post_details" in sql for sql in executed_sqls)
        has_post_prices = any("INSERT INTO post_prices" in sql for sql in executed_sqls)
        has_post_locations = any("post_locations" in sql for sql in executed_sqls)

        self.assertTrue(has_post_addresses, "Phải ghi nhận địa chỉ vào bảng post_addresses")
        self.assertTrue(has_post_details, "Phải ghi nhận chi tiết diện tích vào bảng post_details")
        self.assertTrue(has_post_prices, "Phải ghi nhận giá vào bảng post_prices")
        self.assertFalse(has_post_locations, "Tuyệt đối không được phụ thuộc vào bảng cũ post_locations")


if __name__ == "__main__":
    unittest.main()
