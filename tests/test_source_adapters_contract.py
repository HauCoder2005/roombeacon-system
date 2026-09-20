import json
import unittest

from roombeacon_crawler.enums.crawl_target_type import CrawlTargetType
from roombeacon_crawler.domain.errors.domain_error import ParseError
from roombeacon_crawler.sources.base import BaseSourceAdapter, SourcePagination
from roombeacon_crawler.sources.batdongsan.adapter import (
    BatDongSanSourceAdapter,
)
from roombeacon_crawler.sources.batdongsan.discovery.date_interpreter import (
    BatDongSanDateInterpreter,
)
from roombeacon_crawler.sources.batdongsan.discovery.pagination import (
    BatDongSanPagination,
)
from roombeacon_crawler.sources.muaban.adapter import MuabanSourceAdapter
from roombeacon_crawler.sources.muaban.discovery.date_interpreter import (
    MuabanDateInterpreter,
)
from roombeacon_crawler.sources.muaban.discovery.pagination import (
    MuabanPagination,
)
from roombeacon_crawler.sources.muaban.parsers.listing_parser import (
    MuabanListingParser,
)
from roombeacon_crawler.sources.nhatot.adapter import NhatotSourceAdapter
from roombeacon_crawler.sources.nhatrovn.adapter import NhatroVNSourceAdapter
from roombeacon_crawler.sources.phongtro123.adapter import (
    Phongtro123SourceAdapter,
)
from roombeacon_crawler.sources.phongtro123.discovery.pagination import (
    Phongtro123Pagination,
)
from roombeacon_crawler.sources.registry import source_registry


class TestSourceAdaptersContract(unittest.TestCase):
    """Kiểm tra hợp đồng BaseSourceAdapter và SourcePagination trên toàn bộ sources."""

    def test_all_adapters_satisfy_base_contract(self) -> None:
        adapter_classes = source_registry.get_registered_adapters()
        self.assertEqual(len(adapter_classes), 12)

        for adapter_cls in adapter_classes:
            with self.subTest(adapter=adapter_cls.__name__):
                self.assertTrue(issubclass(adapter_cls, BaseSourceAdapter))
                self.assertTrue(bool(adapter_cls.SOURCE_NAME))
                self.assertTrue(len(adapter_cls.DOMAINS) > 0)
                self.assertTrue(bool(adapter_cls.DEFAULT_BASE_URL))

                # Khởi tạo instance
                instance = adapter_cls()
                self.assertTrue(hasattr(instance, "settings"))
                self.assertTrue(hasattr(instance, "listing_parser"))
                self.assertTrue(hasattr(instance, "detail_parser"))
                self.assertTrue(hasattr(instance, "metadata_parser"))
                self.assertTrue(hasattr(instance, "date_interpreter"))

                # Kiểm tra tuân thủ SourcePagination protocol
                self.assertTrue(hasattr(instance, "pagination"))
                self.assertTrue(isinstance(instance.pagination, SourcePagination))
                self.assertTrue(callable(getattr(instance.pagination, "build_page_url", None)))
                self.assertTrue(callable(getattr(instance.pagination, "has_next_page", None)))

    def test_batdongsan_url_classification_and_support(self) -> None:
        adapter = BatDongSanSourceAdapter()

        # Support check
        self.assertTrue(BatDongSanSourceAdapter.supports("https://batdongsan.com.vn/cho-thue-nha-tro-phong-tro"))
        self.assertTrue(BatDongSanSourceAdapter.supports("https://www.batdongsan.com.vn/cho-thue-can-ho-chung-cu"))
        self.assertFalse(BatDongSanSourceAdapter.supports("https://nhatrovn.vn/cho-thue-phong-tro/"))

        # Listing classification
        self.assertEqual(
            adapter.classify_url("https://batdongsan.com.vn/cho-thue-nha-tro-phong-tro-tp-hcm"),
            CrawlTargetType.LISTING_PAGE,
        )
        self.assertEqual(
            adapter.classify_url("https://batdongsan.com.vn/cho-thue-can-ho-chung-cu-ha-noi"),
            CrawlTargetType.LISTING_PAGE,
        )

        # Detail classification
        self.assertEqual(
            adapter.classify_url("https://batdongsan.com.vn/cho-thue-phong-tro-quan-1/phong-tro-cao-cap-pr12345678"),
            CrawlTargetType.DETAIL_PAGE,
        )

        # Unsupported path on domain
        self.assertEqual(
            adapter.classify_url("https://batdongsan.com.vn/tin-tuc/thi-truong-bat-dong-san"),
            CrawlTargetType.UNSUPPORTED,
        )

    def test_muaban_url_classification_and_support(self) -> None:
        adapter = MuabanSourceAdapter()

        # Support check
        self.assertTrue(MuabanSourceAdapter.supports("https://muaban.net/bat-dong-san/cho-thue-phong-tro-nha-tro"))
        self.assertTrue(MuabanSourceAdapter.supports("https://www.muaban.net/cho-thue-nha-dat"))
        self.assertFalse(MuabanSourceAdapter.supports("https://batdongsan.com.vn/"))
        self.assertEqual(
            adapter.scheduled_targets()[0].url,
            "https://muaban.net/bat-dong-san/cho-thue-nha-tro-phong-tro-ho-chi-minh",
        )

        # Listing classification
        self.assertEqual(
            adapter.classify_url("https://muaban.net/bat-dong-san/cho-thue-phong-tro-nha-tro-tp-hcm"),
            CrawlTargetType.LISTING_PAGE,
        )

        # Detail classification
        self.assertEqual(
            adapter.classify_url("https://muaban.net/bat-dong-san/cho-thue-phong-tro-quan-tan-binh-id68291034"),
            CrawlTargetType.DETAIL_PAGE,
        )

        # Unsupported path on domain
        self.assertEqual(
            adapter.classify_url("https://muaban.net/viec-lam/tuyen-dung-nhan-vien"),
            CrawlTargetType.UNSUPPORTED,
        )

    def test_muaban_parser_reads_current_embedded_listing_payload(self) -> None:
        payload = {
            "props": {
                "pageProps": {
                    "classified": {
                        "items": [
                            {
                                "id": 71228278,
                                "url": "/bat-dong-san/example-id71228278",
                                "title": "Rental title",
                                "price_display": "3 million",
                                "location": "District 4",
                                "publish_display": "Today",
                                "covers": ["/images/example.jpg"],
                            }
                        ]
                    }
                }
            }
        }
        html = (
            '<html><script id="__NEXT_DATA__" type="application/json">'
            + json.dumps(payload)
            + "</script></html>"
        )

        cards = MuabanListingParser().parse(
            html,
            "https://muaban.net/bat-dong-san/rentals",
        )

        self.assertEqual(len(cards), 1)
        self.assertEqual(cards[0].listing_id, "71228278")
        self.assertEqual(
            cards[0].detail_url,
            "https://muaban.net/bat-dong-san/example-id71228278",
        )

    def test_muaban_parser_accepts_structurally_valid_empty_payload(self) -> None:
        payload = {
            "props": {"pageProps": {"classified": {"items": []}}}
        }
        html = (
            '<html><script id="__NEXT_DATA__" type="application/json">'
            + json.dumps(payload)
            + "</script></html>"
        )

        cards = MuabanListingParser().parse(
            html,
            "https://muaban.net/bat-dong-san/rentals",
        )

        self.assertEqual(cards, [])

    def test_muaban_parser_rejects_missing_or_incompatible_schema(self) -> None:
        with self.assertRaises(ParseError):
            MuabanListingParser().parse(
                "",
                "https://muaban.net/bat-dong-san/rentals",
            )
        with self.assertRaises(ParseError):
            MuabanListingParser().parse(
                "<html><body>no embedded listing structure</body></html>",
                "https://muaban.net/bat-dong-san/rentals",
            )

        invalid_payloads = (
            {"props": {"pageProps": {}}},
            {"props": {"pageProps": {"classified": {"items": {}}}}},
        )

        for payload in invalid_payloads:
            with self.subTest(payload=payload):
                html = (
                    '<html><script id="__NEXT_DATA__" type="application/json">'
                    + json.dumps(payload)
                    + "</script></html>"
                )
                with self.assertRaises(ParseError):
                    MuabanListingParser().parse(
                        html,
                        "https://muaban.net/bat-dong-san/rentals",
                    )

    def test_nhatrovn_url_classification_and_support(self) -> None:
        adapter = NhatroVNSourceAdapter()
        self.assertTrue(NhatroVNSourceAdapter.supports("https://nhatrovn.vn/cho-thue-phong-tro/"))
        self.assertEqual(
            adapter.classify_url("https://nhatrovn.vn/cho-thue-phong-tro/ho-chi-minh/"),
            CrawlTargetType.LISTING_PAGE,
        )
        self.assertEqual(
            adapter.classify_url("https://nhatrovn.vn/cho-thue-phong-tro/ho-chi-minh/chi-tiet/6a83dc4c/"),
            CrawlTargetType.DETAIL_PAGE,
        )
        self.assertEqual(
            adapter.classify_url("https://nhatrovn.vn/chinh-sach-bao-mat/"),
            CrawlTargetType.UNSUPPORTED,
        )

    def test_nhatot_url_classification_and_support(self) -> None:
        adapter = NhatotSourceAdapter()
        self.assertTrue(NhatotSourceAdapter.supports("https://www.nhatot.com/thue-phong-tro"))
        self.assertEqual(
            adapter.classify_url("https://www.nhatot.com/thue-phong-tro-tp-ho-chi-minh"),
            CrawlTargetType.LISTING_PAGE,
        )
        self.assertEqual(
            adapter.classify_url("https://www.nhatot.com/12345678.htm"),
            CrawlTargetType.DETAIL_PAGE,
        )

    def test_phongtro123_url_classification_and_support(self) -> None:
        adapter = Phongtro123SourceAdapter()
        self.assertTrue(Phongtro123SourceAdapter.supports("https://phongtro123.com/cho-thue-phong-tro"))
        self.assertEqual(
            adapter.classify_url("https://phongtro123.com/cho-thue-phong-tro-ho-chi-minh"),
            CrawlTargetType.LISTING_PAGE,
        )
        self.assertEqual(
            adapter.classify_url("https://phongtro123.com/cho-thue-phong-tro-quan-1-pr12345"),
            CrawlTargetType.DETAIL_PAGE,
        )

    def test_phongtro123_scheduled_target_prioritizes_newest_listings(self) -> None:
        """Scheduler phải bắt đầu từ luồng tin mới thay vì luồng đề xuất."""
        target = Phongtro123SourceAdapter().scheduled_targets()[0]

        self.assertEqual(
            target.url,
            "https://phongtro123.com/tinh-thanh/ho-chi-minh?orderby=moi-nhat",
        )

    def test_phongtro123_pagination_preserves_newest_order(self) -> None:
        """Phân trang phải giữ bộ lọc mới nhất trong toàn bộ lượt crawl."""
        pagination = Phongtro123Pagination()
        base_url = (
            "https://phongtro123.com/tinh-thanh/ho-chi-minh?orderby=moi-nhat"
        )

        self.assertEqual(
            pagination.build_page_url(base_url=base_url, page_number=1),
            base_url,
        )
        self.assertEqual(
            pagination.build_page_url(base_url=base_url, page_number=2),
            "https://phongtro123.com/tinh-thanh/ho-chi-minh"
            "?orderby=moi-nhat&page=2",
        )

    def test_batdongsan_pagination(self) -> None:
        pagination = BatDongSanPagination()
        base_url = "https://batdongsan.com.vn/cho-thue-nha-tro-phong-tro-tp-hcm"
        self.assertEqual(
            pagination.build_page_url(base_url=base_url, page_number=1),
            "https://batdongsan.com.vn/cho-thue-nha-tro-phong-tro-tp-hcm",
        )
        self.assertEqual(
            pagination.build_page_url(base_url=base_url, page_number=2),
            "https://batdongsan.com.vn/cho-thue-nha-tro-phong-tro-tp-hcm/p2",
        )
        self.assertEqual(
            pagination.build_page_url(base_url="https://batdongsan.com.vn/cho-thue-nha-tro-phong-tro-tp-hcm/p2", page_number=3),
            "https://batdongsan.com.vn/cho-thue-nha-tro-phong-tro-tp-hcm/p3",
        )
        self.assertTrue(pagination.has_next_page(current_page=1, max_pages=5, current_items_count=20))
        self.assertFalse(pagination.has_next_page(current_page=5, max_pages=5, current_items_count=20))
        self.assertFalse(pagination.has_next_page(current_page=2, max_pages=5, current_items_count=0))

    def test_muaban_pagination(self) -> None:
        pagination = MuabanPagination()
        base_url = "https://muaban.net/bat-dong-san/cho-thue-phong-tro-nha-tro-tp-hcm"
        self.assertEqual(
            pagination.build_page_url(base_url=base_url, page_number=1),
            "https://muaban.net/bat-dong-san/cho-thue-phong-tro-nha-tro-tp-hcm",
        )
        self.assertEqual(
            pagination.build_page_url(base_url=base_url, page_number=2),
            "https://muaban.net/bat-dong-san/cho-thue-phong-tro-nha-tro-tp-hcm?page=2",
        )
        self.assertTrue(pagination.has_next_page(current_page=1, max_pages=5, current_items_count=20))
        self.assertFalse(pagination.has_next_page(current_page=5, max_pages=5, current_items_count=20))
        self.assertFalse(pagination.has_next_page(current_page=2, max_pages=5, current_items_count=0))

    def test_batdongsan_date_interpreter(self) -> None:
        interpreter = BatDongSanDateInterpreter()
        self.assertIsNotNone(interpreter.interpret("Hôm nay"))
        self.assertIsNotNone(interpreter.interpret("Hôm qua"))
        self.assertIsNotNone(interpreter.interpret("3 ngày trước"))
        self.assertIsNotNone(interpreter.interpret("15/08/2026"))
        self.assertIsNone(interpreter.interpret(None))

    def test_muaban_date_interpreter(self) -> None:
        interpreter = MuabanDateInterpreter()
        self.assertIsNotNone(interpreter.interpret("Hôm nay"))
        self.assertIsNotNone(interpreter.interpret("2 giờ trước"))
        self.assertIsNotNone(interpreter.interpret("30 phút trước"))
        self.assertIsNotNone(interpreter.interpret("18/08/2026"))
        self.assertIsNone(interpreter.interpret(None))


if __name__ == "__main__":
    unittest.main()
