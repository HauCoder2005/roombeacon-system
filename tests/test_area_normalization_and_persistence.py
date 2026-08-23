import unittest
from unittest.mock import MagicMock, call
from roombeacon_crawler.infrastructure.mysql.mappers.bronze_mapper import MySQLBronzeMapper
from roombeacon_crawler.infrastructure.mysql.repositories.post_children_repository import MySQLPostChildrenRepository
from roombeacon_crawler.domain.models.bronze_observation import BronzeObservation


class TestAreaNormalizationAndPersistence(unittest.TestCase):
    """Kiểm thử tính năng chuẩn hóa diện tích an toàn và cơ chế bảo vệ persistence."""

    def test_valid_integer_area(self):
        self.assertEqual(MySQLBronzeMapper.parse_numeric_area("25 m²"), 25.0)
        self.assertEqual(MySQLBronzeMapper.parse_numeric_area("30m2"), 30.0)
        self.assertEqual(MySQLBronzeMapper.parse_numeric_area("45 m"), 45.0)

    def test_valid_decimal_area(self):
        self.assertEqual(MySQLBronzeMapper.parse_numeric_area("25.5 m²"), 25.5)
        self.assertEqual(MySQLBronzeMapper.parse_numeric_area("100.25 m2"), 100.25)

    def test_comma_decimal_area(self):
        self.assertEqual(MySQLBronzeMapper.parse_numeric_area("25,5 m²"), 25.5)
        self.assertEqual(MySQLBronzeMapper.parse_numeric_area("40,75m2"), 40.75)

    def test_missing_and_empty_area(self):
        self.assertIsNone(MySQLBronzeMapper.parse_numeric_area(None))
        self.assertIsNone(MySQLBronzeMapper.parse_numeric_area(""))
        self.assertIsNone(MySQLBronzeMapper.parse_numeric_area("   "))

    def test_non_area_text(self):
        self.assertIsNone(MySQLBronzeMapper.parse_numeric_area("Liên hệ"))
        self.assertIsNone(MySQLBronzeMapper.parse_numeric_area("Thỏa thuận"))
        self.assertIsNone(MySQLBronzeMapper.parse_numeric_area("Thương lượng"))
        self.assertIsNone(MySQLBronzeMapper.parse_numeric_area("N/A"))
        self.assertIsNone(MySQLBronzeMapper.parse_numeric_area("abc"))

    def test_absurd_overflow_number(self):
        # Trường hợp thực tế gây lỗi DataError 1264 Out of range trong Airflow
        self.assertIsNone(MySQLBronzeMapper.parse_numeric_area("120202748m"))
        self.assertIsNone(MySQLBronzeMapper.parse_numeric_area("0912345678m"))
        self.assertIsNone(MySQLBronzeMapper.parse_numeric_area("999999999 m2"))

    def test_large_but_plausible_area(self):
        self.assertEqual(MySQLBronzeMapper.parse_numeric_area("500 m²"), 500.0)
        self.assertEqual(MySQLBronzeMapper.parse_numeric_area("2000 m2"), 2000.0)
        self.assertEqual(MySQLBronzeMapper.parse_numeric_area("50000 m²"), 50000.0)

    def test_persistence_defensive_guard_preserves_raw_and_nulls_invalid_area(self):
        mock_conn = MagicMock()
        repo = MySQLPostChildrenRepository(connection=mock_conn)

        obs = BronzeObservation(
            source="phongtro123",
            listing_id="12345",
            run_id="run_test",
            url="https://example.com/item",
            area_raw="120202748m",
            price_raw="4.5 triệu/tháng",
            address_raw="Quận 10, TP.HCM",
        )

        repo.persist_children(obs, post_id=100, observation_id=200)

        # Kiểm tra câu lệnh INSERT INTO post_details được gọi
        details_call = None
        for call_args in mock_conn.execute.call_args_list:
            sql_text = str(call_args[0][0])
            if "INSERT INTO post_details" in sql_text:
                details_call = call_args
                break

        self.assertIsNotNone(details_call, "INSERT INTO post_details không được gọi!")
        params = details_call[0][1]
        
        # Bất biến cốt lõi: area_raw giữ nguyên vẹn 100%, area_val trở thành NULL
        self.assertEqual(params["area_raw"], "120202748m")
        self.assertIsNone(params["area_val"])
        self.assertEqual(params["post_id"], 100)
        self.assertEqual(params["version_id"], 200)

    def test_phongtro123_parser_no_cross_field_contamination(self):
        from roombeacon_crawler.sources.phongtro123.parsers.listing_parser import Phongtro123ListingParser

        html_sample = """
        <ul class="post-listing">
            <li class="post-item">
                <h3 class="post-title"><a href="/cho-thue-phong-tro-hcm/phong-tro-gia-re-pr120202748.html">Phòng trọ đẹp gần ĐH Bách Khoa</a></h3>
                <div class="meta-row">
                    <span class="post-price">4.3 triệu/tháng</span>
                    <span class="post-acreage">28 m2</span>
                    <span class="post-location">Quận 10, Hồ Chí Minh</span>
                </div>
                <div class="line-clamp-1">4.3 triệu/tháng 28 m 2</div>
                <div class="user-info">
                    <span class="author-name">Anh Nam Chủ Nhà</span>
                    <time class="post-time">09:14, 13/11/2025</time>
                </div>
            </li>
        </ul>
        """

        parser = Phongtro123ListingParser()
        cards = parser.parse(html_sample, "https://phongtro123.com/tinh-thanh/ho-chi-minh")
        self.assertEqual(len(cards), 1)
        c = cards[0]

        self.assertEqual(c.listing_id, "120202748")
        self.assertEqual(c.price_raw, "4.3 triệu/tháng")
        self.assertEqual(c.area_raw, "28 m2")
        self.assertEqual(c.location_raw, "Quận 10, Hồ Chí Minh")
        self.assertEqual(c.seller_name_raw, "Anh Nam Chủ Nhà")
        self.assertEqual(c.posted_at_raw, "09:14, 13/11/2025")

        # Kiểm tra chuẩn hóa diện tích
        self.assertEqual(MySQLBronzeMapper.parse_numeric_area(c.area_raw), 28.0)


if __name__ == "__main__":
    unittest.main()
