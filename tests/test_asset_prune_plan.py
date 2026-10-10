"""Prune plan: stored objects that are not the listing's own photos, never anything unknown."""

from roombeacon_crawler.application.assets.prune_plan import plan_prune
from roombeacon_crawler.models.asset_item import AssetItem

OWN = "https://cloud.mogi.vn/images/2026/09/27/213/own.jpg"
LOGO = "https://mogi.vn/content/Images/logo.svg"
BADGE = "https://images.dmca.com/Badges/dmca_protected_sml_120m.png"


def _key(source, sid, position, url, ext="jpg"):
    return AssetItem.generate_object_key(source, sid, position, url, ext=ext)


def test_plan_lists_only_objects_that_are_not_own_photos():
    keys = [_key("mogi", "22753131", 1, BADGE, "png"), _key("mogi", "22753131", 3, OWN)]
    images = {("mogi", "22753131"): [(1, BADGE), (2, LOGO), (3, OWN)]}

    plan = plan_prune(keys, lambda source, sid: [images[(source, sid)]] if (source, sid) in images else None)

    assert plan.keys == [keys[0]]
    assert plan.per_source == {"mogi": {"objects": 2, "prune": 1, "unknown_listing": 0}}


def test_listing_missing_from_bronze_is_left_alone():
    keys = [_key("mogi", "999", 1, BADGE, "png")]

    plan = plan_prune(keys, lambda *_: None)

    assert plan.keys == []
    assert plan.per_source["mogi"]["unknown_listing"] == 1


def test_nested_listing_ids_and_foreign_keys_are_handled():
    sid = "tinh-thanh/ho-chi-minh/phong-a"
    related = "https://pt123.cdn.static123.com/images/thumbs/450x300/fit/2026/10/10/other.jpg"
    keys = [_key("phongtro123", sid, 1, related), "phongtro123/readme.txt", "not-an-image-key"]

    detail = [(1, "/images/logo-phongtro.svg"), (2, related)]
    plan = plan_prune(keys, lambda source, listing: [detail] if (source, listing) == ("phongtro123", sid) else None)

    assert plan.keys == [keys[0]]
