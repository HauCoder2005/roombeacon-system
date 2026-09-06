"""Regressions for bounded, identity-preserving address recovery selection."""

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import SimpleNamespace

from roombeacon_crawler.enums.crawl_target_type import CrawlTargetType


def _load_script():
    path = Path("scripts/recover_missing_full_addresses.py")
    spec = spec_from_file_location("recover_missing_full_addresses", path)
    module = module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_recovery_keeps_stable_identity_and_skips_pending_or_profiles():
    module = _load_script()
    adapter = SimpleNamespace(
        CAPABILITIES=SimpleNamespace(detail_fetch_supported=True),
        classify_url=lambda url: (
            CrawlTargetType.UNSUPPORTED
            if "/moi-gioi/" in url
            else CrawlTargetType.DETAIL_PAGE
        ),
    )
    registry = SimpleNamespace(get=lambda source: lambda: adapter)
    repository = SimpleNamespace(
        _load=lambda source, target: {
            "pending-id": {"status": "PENDING"},
            "terminal-id": {"status": "TERMINAL_FAILED"},
        }
    )
    rows = [
        SimpleNamespace(source="cafeland", platform_post_id="stable-id", url="https://example.test/listing.html", title_raw="Listing"),
        SimpleNamespace(source="cafeland", platform_post_id="pending-id", url="https://example.test/pending.html", title_raw="Pending"),
        SimpleNamespace(source="cafeland", platform_post_id="terminal-id", url="https://example.test/terminal.html", title_raw="Terminal"),
        SimpleNamespace(source="cafeland", platform_post_id="profile-id", url="https://example.test/moi-gioi/profile.html", title_raw="Profile"),
    ]

    selected, reasons = module.select_recovery_items(
        rows,
        registry=registry,
        repository=repository,
        target_id="hcm_phongtro",
        limit=10,
    )

    assert [item.platform_post_id for item in selected] == ["stable-id"]
    assert selected[0].reason == "LATEST_FULL_ADDRESS_MISSING"
    assert reasons == {
        "ALREADY_PENDING": 1,
        "TERMINAL": 1,
        "INVALID_OR_NON_LISTING_URL": 1,
    }

from roombeacon_crawler.sources.cafeland.parsers.listing_parser import CafelandListingParser
from roombeacon_crawler.sources.chothuenha.parsers.listing_parser import ChothuenhaListingParser

def test_cafeland_card_location_raw_extracted():
    html = """
    <div class="row-item">
        <a href="https://nhadat.cafeland.vn/cho-thue-phong-tro-abc-123.html" title="Title">Title</a>
        <div class="info-location float-start">
            Phương Liễu, Bắc Ninh
        </div>
    </div>
    """
    parser = CafelandListingParser("cafeland")
    cards = parser.parse(html, "https://nhadat.cafeland.vn/cho-thue-nha-dat/")
    assert len(cards) == 1
    assert cards[0].location_raw == "Phương Liễu, Bắc Ninh"

def test_chothuenha_card_location_raw_extracted():
    html = """
    <div class="dv-bds">
        <figure class="home-thumb">
            <a href="https://chothuenha.com.vn/phong-tro-quan-12-cvpm-quang-trung-78905">Title</a>
        </figure>
        <div class="dv-bds-autho">
            <a href="https://chothuenha.com.vn/cho-thue-nha-quan-1-ho-chi-minh">Quận 1, Hồ Chí Minh</a>
        </div>
    </div>
    """
    parser = ChothuenhaListingParser("chothuenha")
    cards = parser.parse(html, "https://chothuenha.com.vn/cho-thue-phong-tro-nha-tro-ho-chi-minh")
    assert len(cards) == 1
    assert cards[0].location_raw == "Quận 1, Hồ Chí Minh"
