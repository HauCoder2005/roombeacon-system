import unittest

from roombeacon_crawler.enums.crawl_target_type import CrawlTargetType
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
from roombeacon_crawler.sources.nhatot.adapter import NhatotSourceAdapter
from roombeacon_crawler.sources.nhatrovn.adapter import NhatroVNSourceAdapter
from roombeacon_crawler.sources.phongtro123.adapter import (
    Phongtro123SourceAdapter,
)
from roombeacon_crawler.sources.registry import source_registry


class TestSourceAdaptersContract(unittest.TestCase):
    """Kiểm tra tính thống nhất của hợp đồng BaseSourceAdapter và SourcePagination trên toàn bộ 5 sources."""

    def test_all_adapters_satisfy_base_contract(self) -> None:
        adapter_classes = source_registry.get_registered_adapters()
        self.assertEqual(len(adapter_classes), 5)

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
