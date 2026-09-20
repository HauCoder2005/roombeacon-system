"""Contract regressions for the seven audited rental source integrations."""

from pathlib import Path

import pytest

from roombeacon_crawler.enums.crawl_target_type import CrawlTargetType
from roombeacon_crawler.enums.source_access_profile import SourceAccessProfile
from roombeacon_crawler.sources.registry import SourceRegistry


SOURCE_CASES = {
    "chothuenha": {
        "listing": '<div class="dv-bds"><a href="/phong-tro-quan-12-78905" title="Phòng Quận 12">Phòng Quận 12</a><span class="price">2,9 Triệu</span><figure class="home-thumb"><img src="/room.jpg"></figure></div>',
        "detail": '<h1>Phòng Quận 12</h1><div class="pd-map">86/52 Đường Tân Chánh Hiệp 36, Quận 12, Hồ Chí Minh</div><div class="showText">Mô tả thật</div><footer class="address">Địa chỉ văn phòng gây nhiễu</footer>',
        "id": "78905", "page2": "?page=2",
    },
    "tromoi": {
        "listing": '<article class="hostel-item"><a class="hostel-item__link" href="/phong-tro/nha-tro-105-ung-van-khiem">Nhà trọ 105 Ung Văn Khiêm</a><span class="hostel-item__price">2,7 triệu</span><span class="hostel-item__address">Bình Thạnh</span></article>',
        "detail": '<h1>Nhà trọ</h1><div class="content-detail"><p><strong>Địa chỉ:</strong> 105 Ung Văn Khiêm, Bình Thạnh <strong>Giá:</strong> 2,7 triệu</p></div><footer class="address">Địa chỉ công ty gây nhiễu</footer>',
        "id": "phong-tro/nha-tro-105-ung-van-khiem", "page2": "?page=2",
    },
    "guland": {
        "listing": '<div class="c-sdb-card"><a href="/signin">Thích</a><a href="/post/phong-co-gac-2550933">Cho thuê phòng có gác</a><span class="data-type-price">3,2 triệu</span><span class="data-type-adr">Phường An Hội Tây</span></div>',
        "detail": '<h1 class="dtl-tle">Cho thuê phòng có gác</h1><div class="dtl-stl__row">Phường An Hội Tây, TP. Hồ Chí Minh</div><footer class="address">94 Đường 15, địa chỉ công ty</footer>',
        "id": "2550933", "page2": None,
    },
    "chothuephongtro": {
        "listing": '<article class="post-item"><h3 class="post-title"><a href="/phong-studio-pr169591.html">Phòng studio Bình Thạnh</a></h3><span class="post-price">7,5 triệu</span><span class="acreage">30 m2</span><span class="location">Bình Thạnh</span></article>',
        "detail": '<h1>Phòng studio</h1><table><tr><td class="td-name">Địa chỉ</td><td class="td-value">220 Xô Viết Nghệ Tĩnh, Bình Thạnh</td></tr></table><footer class="address">Địa chỉ doanh nghiệp</footer>',
        "id": "169591", "page2": "?page=2",
    },
    "mogi": {
        "listing": '<div class="prop-info"><a class="link-overlay" href="/quan-3/thue-phong/room-id22744154">Cho thuê phòng Quận 3</a><div class="price">2,6 triệu</div><div class="prop-addr">Quận 3</div></div>',
        "detail": '<h1>Cho thuê phòng Quận 3</h1><div class="address">Nguyễn Thiện Thuật, Phường 3, Quận 3</div><div class="info-content-body">Mô tả phòng</div><footer>Địa chỉ công ty gây nhiễu</footer>',
        "id": "22744154", "page2": "?cp=2",
    },
    "cafeland": {
        "listing": '<div class="row-item"><a href="/phong-tro-hoc-mon-3144910.html">Phòng trọ Hóc Môn</a><div class="reals-price">2,4 triệu</div><div class="reals-address">Hóc Môn</div></div>',
        "detail": '<h1>Phòng trọ Hóc Môn</h1><script type="application/ld+json">{"@type":"House","address":{"streetAddress":"12 Song Hành","addressLocality":"Hóc Môn","addressRegion":"Hồ Chí Minh"}}</script><div class="reals-description">Mô tả dự án</div><footer class="address">Địa chỉ tòa soạn</footer>',
        "id": "3144910", "page2": "/page-2/",
    },
}


@pytest.mark.parametrize("source", SOURCE_CASES)
def test_new_source_listing_and_stable_identity(source):
    adapter = SourceRegistry().get(source)()
    case = SOURCE_CASES[source]
    first = adapter.listing_parser.parse(case["listing"], adapter.DEFAULT_BASE_URL)
    second = adapter.listing_parser.parse(case["listing"], adapter.DEFAULT_BASE_URL)
    assert len(first) == 1
    assert first[0].listing_id == case["id"] == second[0].listing_id
    assert first[0].title_raw
    assert first[0].detail_url.startswith("https://")


@pytest.mark.parametrize("source", SOURCE_CASES)
def test_new_source_detail_prefers_listing_address_over_contamination(source):
    adapter = SourceRegistry().get(source)()
    case = SOURCE_CASES[source]
    detail = adapter.detail_parser.parse(
        case["detail"], detail_url="https://" + adapter.DOMAINS[0] + "/detail", listing_id=case["id"]
    )
    assert detail is not None
    assert detail.listing_id == case["id"]
    assert detail.address_raw
    assert "công ty" not in detail.address_raw.casefold()
    assert "doanh nghiệp" not in detail.address_raw.casefold()
    assert "tòa soạn" not in detail.address_raw.casefold()


@pytest.mark.parametrize("source", SOURCE_CASES)
def test_new_source_missing_fields_are_not_invented(source):
    adapter = SourceRegistry().get(source)()
    assert adapter.listing_parser.parse("<html><body></body></html>", adapter.DEFAULT_BASE_URL) == []
    detail = adapter.detail_parser.parse("<h1>Only title</h1>", detail_url=adapter.DEFAULT_BASE_URL, listing_id="known")
    assert detail is not None
    assert detail.price_raw is None
    assert detail.address_raw is None


def test_chothuephongtro_extracts_address_from_location_section():
    adapter = SourceRegistry().get("chothuephongtro")()
    detail = adapter.detail_parser.parse(
        """
        <section class="post-section">
          <div class="section-header">Vị trí phòng trọ</div>
          <div class="section-content">
            Đường Sông Đáy, Phường 2, Tân Bình, Hồ Chí Minh
          </div>
        </section>
        <footer><div class="location">Công ty TNHH Cho Thuê Phòng Trọ</div></footer>
        """,
        detail_url="https://chothuephongtro.me/phong-pr123456.html",
        listing_id="123456",
    )

    assert detail.address_raw == (
        "Đường Sông Đáy, Phường 2, Tân Bình, Hồ Chí Minh"
    )


def test_chothuephongtro_does_not_use_footer_location_as_listing_address():
    adapter = SourceRegistry().get("chothuephongtro")()
    detail = adapter.detail_parser.parse(
        '<h1>Phòng trọ</h1><footer><div class="location">'
        "Công ty TNHH Cho Thuê Phòng Trọ</div></footer>",
        detail_url="https://chothuephongtro.me/phong-pr123456.html",
        listing_id="123456",
    )

    assert detail.address_raw is None


@pytest.mark.parametrize("source", SOURCE_CASES)
def test_new_source_pagination_matches_audited_policy(source):
    adapter = SourceRegistry().get(source)()
    page2 = adapter.pagination.build_page_url(adapter.DEFAULT_BASE_URL, 2)
    expected = SOURCE_CASES[source]["page2"]
    if expected is None:
        assert adapter.CAPABILITIES.supports_pagination is False
    else:
        assert expected in page2
        assert adapter.CAPABILITIES.supports_pagination is True


def test_all_twelve_sources_are_registered_with_conservative_activation():
    registry = SourceRegistry()
    assert registry.list_sources() == sorted({
        "nhatot", "nhatrovn", "phongtro123", "batdongsan", "muaban",
        "chothuenha", "tromoi", "guland", "chothuephongtro", "mogi",
        "cafeland", "phongtrotoanquoc",
    })
    for source in SOURCE_CASES:
        seed = registry.get(source)().scheduled_targets()[0]
        assert seed.max_details_per_run == 20
    assert registry.get("phongtrotoanquoc")().CAPABILITIES.access_profile is SourceAccessProfile.ACCESS_CHALLENGED
    assert registry.get("phongtrotoanquoc")().scheduled_targets()[0].enabled is False
    assert registry.get("phongtrotoanquoc")().classify_url(
        "https://phongtrotoanquoc.com/phong-tro/thanh-pho-ho-chi-minh"
    ) is CrawlTargetType.LISTING_PAGE


def test_verified_new_source_batches_are_active():
    registry = SourceRegistry()
    enabled = {
        source for source in (
            "chothuenha", "tromoi", "guland", "chothuephongtro", "mogi",
            "cafeland", "phongtrotoanquoc",
        ) if registry.get(source)().scheduled_targets()[0].enabled
    }
    assert enabled == {
        "chothuenha", "tromoi", "guland", "chothuephongtro", "mogi", "cafeland"
    }


def test_stable_new_sources_use_high_throughput_scheduling_profile():
    registry = SourceRegistry()
    for source in (
        "chothuenha", "tromoi", "chothuephongtro", "mogi", "cafeland",
    ):
        seed = registry.get(source)().scheduled_targets()[0]
        assert seed.interval_minutes == 5
        assert seed.bootstrap_safety_max_pages == 10

    # Guland uses the same effective cadence, while its health cooldown remains
    # an independent access-policy gate.
    guland_seed = registry.get("guland")().scheduled_targets()[0]
    assert guland_seed.interval_minutes == 10

    assert registry.get("nhatot")().scheduled_targets()[0].interval_minutes == 10
    assert registry.get("phongtro123")().scheduled_targets()[0].interval_minutes == 5


def test_chothuenha_numeric_detail_route_is_not_confused_with_category():
    adapter = SourceRegistry().get("chothuenha")()
    assert adapter.classify_url(adapter.DEFAULT_BASE_URL) is CrawlTargetType.LISTING_PAGE
    assert adapter.classify_url(
        "https://chothuenha.com.vn/phong-tro-quan-12-cvpm-quang-trung-78905"
    ) is CrawlTargetType.DETAIL_PAGE


def test_cafeland_broker_profile_is_not_a_rental_detail():
    adapter = SourceRegistry().get("cafeland")()
    assert adapter.classify_url(
        "https://nhadat.cafeland.vn/moi-gioi/profile.html"
    ) is CrawlTargetType.UNSUPPORTED


def test_cafeland_listing_parser_rejects_broker_profile_cards():
    adapter = SourceRegistry().get("cafeland")()
    rows = adapter.listing_parser.parse(
        '''
        <div class="row-item">
          <a href="/moi-gioi/cat-binh-276014.html">Cát Bình</a>
        </div>
        <div class="row-item">
          <a href="/phong-tro-hoc-mon-3144910.html">Phòng trọ Hóc Môn</a>
        </div>
        ''',
        adapter.DEFAULT_BASE_URL,
    )

    assert [(row.listing_id, row.title_raw) for row in rows] == [
        ("3144910", "Phòng trọ Hóc Môn")
    ]


def test_cafeland_detail_parser_extracts_labeled_area_from_information_block():
    adapter = SourceRegistry().get("cafeland")()
    detail = adapter.detail_parser.parse(
        '''
        <div class="reals-info-group">
          <div class="col-item">
            <div class="infor-note">Giá bán</div><div class="infor-data">8 triệu</div>
          </div>
          <div class="col-item">
            <div class="infor-note">Diện tích</div><div class="infor-data">91m2</div>
          </div>
        </div>
        ''',
        detail_url="https://nhadat.cafeland.vn/listing-3132271.html",
    )

    assert detail.price_raw == "8 triệu"
    assert detail.area_raw == "91m2"


def test_cafeland_pagination_uses_source_next_anchor_and_stops_at_last_page():
    adapter = SourceRegistry().get("cafeland")()

    assert adapter.pagination.build_page_url(adapter.DEFAULT_BASE_URL, 2).endswith(
        "/page-2/"
    )
    assert adapter.pagination.build_page_url(adapter.DEFAULT_BASE_URL, 3).endswith(
        "/page-3/"
    )
    assert adapter.pagination.has_next_page(
        current_page=1,
        max_pages=10,
        current_items_count=20,
        raw_html='<ul class="pagination"><li><a href="/page-2/">2</a></li></ul>',
    )
    assert not adapter.pagination.has_next_page(
        current_page=3,
        max_pages=10,
        current_items_count=20,
        raw_html='<ul class="pagination"><li><a href="/page-2/">2</a></li><li class="active"><a>3</a></li></ul>',
    )


def test_crawler_dag_declares_operator_facing_task_ids():
    source = Path("airflow/dags/crawler/roombeacon_crawler.py").read_text(encoding="utf-8")
    for task_id in (
        "01_config_load_sources", "02_config_plan_crawls", "03_crawl_check_eligibility",
        "04_crawl_execute_source", "05_storage_save_bronze", "06_state_update_checkpoint",
        "07_analytics_refresh_duckdb", "08_assets_sync_minio", "09_report_run_summary",
    ):
        assert f'task_id="{task_id}"' in source
