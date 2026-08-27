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
