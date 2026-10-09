"""Domain cards -> JSON. Money is integer VND; unknown statistics are null, never 0."""

from __future__ import annotations

from typing import Any

from ..application.listing_service import ImageSummary, ListingDetail, MarketComparison, Valuation
from ..application.price_estimate_service import EstimateResult
from ..domain.models import (
    DistrictCard,
    ListingCard,
    MarketDay,
    MarketSummary,
    ModelInfo,
    PricePoint,
    PriceStats,
    WardCard,
)
from ..domain.pii import contains_contact_number, mask_contact_numbers
from .envelope import iso


DISTRICTS_PATH = "/api/v1/locations/districts"


def _money(value: float | None) -> int | None:
    return None if value is None else int(round(value))


def price_out(price: PriceStats) -> dict[str, Any]:
    return {
        "currency": "VND",
        "median": _money(price.median),
        "p25": _money(price.p25),
        "p75": _money(price.p75),
        "median_per_m2": _money(price.median_per_m2),
        "median_area_m2": None if price.median_area is None else round(price.median_area, 1),
    }


def cover_out(cover: Any) -> dict[str, Any] | None:
    if cover is None:
        return None
    return {"url": f"/api/v1/listings/{cover.listing_id}/images/{cover.position}", "listing_id": cover.listing_id}


def district_out(card: DistrictCard, cover: Any = None) -> dict[str, Any]:
    return {
        "id": card.id,
        "type": "district",
        "name": card.name,
        "stats": {
            "listing_count": card.listing_count,
            "priced_listing_count": card.priced_listing_count,
            "ward_count": card.ward_count,
        },
        "price": price_out(card.price),
        "cover_image": cover_out(cover),
        "links": {"self": f"{DISTRICTS_PATH}/{card.id}", "wards": f"{DISTRICTS_PATH}/{card.id}/wards"},
    }


def ward_out(card: WardCard, cover: Any = None) -> dict[str, Any]:
    return {
        "id": card.id,
        "type": "ward",
        "name": card.name,
        "district": {"id": card.district_id, "name": card.district_name},
        "stats": {"listing_count": card.listing_count, "priced_listing_count": card.priced_listing_count},
        "price": price_out(card.price),
        "cover_image": cover_out(cover),
        "links": {
            "district": f"{DISTRICTS_PATH}/{card.district_id}",
            "district_wards": f"{DISTRICTS_PATH}/{card.district_id}/wards",
        },
    }


# -- listings, market, estimates -------------------------------------------------

LISTINGS_PATH = "/api/v1/listings"


def _ref(identifier: str | None, name: str | None) -> dict[str, Any] | None:
    return {"id": identifier, "name": name} if identifier and name else None


def _area(value: float | None) -> float | None:
    return None if value is None else round(float(value), 1)


def _public_url(url: str | None) -> str | None:
    """Only absolute http(s) URLs without an embedded phone number leave the API."""
    if not url or contains_contact_number(url):
        return None
    lowered = url.strip().lower()
    return url.strip() if lowered.startswith(("https://", "http://")) else None


def listing_out(card: ListingCard, valuation: Valuation | None, images: ImageSummary | None = None) -> dict[str, Any]:
    """Contact numbers are masked in titles; URLs that embed one are dropped entirely."""
    level = "WARD" if card.ward_id else "DISTRICT" if card.district_id else "UNKNOWN"
    per_m2 = card.price_vnd / card.area_m2 if card.price_vnd and card.area_m2 else None
    return {
        "id": card.id,
        "type": "listing",
        "title": mask_contact_numbers(card.title) or "",
        "source": card.source,
        "source_url": _public_url(card.source_url),
        "price": None if card.price_vnd is None else {"currency": "VND", "amount": _money(card.price_vnd), "period": "month"},
        "area_m2": _area(card.area_m2),
        "price_per_m2": _money(per_m2),
        "location": {
            "level": level,
            "district": _ref(card.district_id, card.district),
            "ward": _ref(card.ward_id, card.ward),
        },
        "intent": card.intent,
        "scope": card.scope,
        "first_observed_at": iso(card.first_observed_at),
        "last_observed_at": iso(card.last_observed_at),
        "active_days": card.active_days,
        "quality": {"price_suitability": card.price_suitability, "duplicate_status": card.duplicate_status},
        "valuation": None if valuation is None else {
            "estimate": _money(valuation.estimate), "delta_pct": valuation.delta_pct, "label": valuation.label,
        },
        "images": None if images is None else {
            "count": images.count,
            "cover": f"{LISTINGS_PATH}/{card.id}/images/{images.cover_position}" if images.cover_position is not None else None,
            "preview": [f"{LISTINGS_PATH}/{card.id}/images/{p}" for p in images.preview_positions],
        },
        "links": {"self": f"{LISTINGS_PATH}/{card.id}", "price_history": f"{LISTINGS_PATH}/{card.id}/price-history"},
    }


def market_out(market: MarketComparison | None) -> dict[str, Any] | None:
    if market is None:
        return None
    return {
        "scope": market.scope, "name": market.name, "median": _money(market.median), "p25": _money(market.p25),
        "p75": _money(market.p75), "listing_count": market.listing_count, "position": market.position,
    }


def listing_detail_out(detail: ListingDetail, images: ImageSummary | None = None) -> dict[str, Any]:
    return {**listing_out(detail.listing, detail.valuation, images), "market": market_out(detail.market)}


def price_point_out(point: PricePoint) -> dict[str, Any]:
    return {
        "observed_at": iso(point.observed_at), "price": _money(point.price), "area_m2": _area(point.area_m2),
        "is_price_change": point.is_price_change, "is_content_change": point.is_content_change,
    }


def summary_out(summary: MarketSummary, district: DistrictCard | None) -> dict[str, Any]:
    return {
        "scope": {"type": "district" if district else "city", "district": _ref(district.id, district.name) if district else None},
        "listing_count": summary.listing_count,
        "priced_listing_count": summary.priced_listing_count,
        "district_count": summary.district_count,
        "price": {"currency": "VND", "median": _money(summary.median), "p25": _money(summary.p25), "p75": _money(summary.p75)},
        "data_from": iso(summary.data_from),
        "data_until": iso(summary.data_until),
    }


def day_out(day: MarketDay) -> dict[str, Any]:
    return {
        "date": day.day.isoformat(), "listings_observed": day.listings_observed, "new_listings": day.new_listings,
        "price_changes": day.price_changes, "median_price": _money(day.median_price),
    }


DISCLAIMER = (
    "Ước tính tham khảo từ mô hình thử nghiệm, không phải giá niêm yết; "
    "khoảng giá chứa giá thật của khoảng 50% tin trong tập kiểm thử."
)


def estimate_out(result: EstimateResult) -> dict[str, Any]:
    info = result.info
    return {
        "estimate": _money(result.prediction.value),
        "range": {"low": _money(result.prediction.low), "high": _money(result.prediction.high), "coverage": info.interval_coverage},
        "inputs_used": {
            "area_m2": float(result.area_m2),
            "district": result.district.name,
            "ward": result.ward.name if result.ward else None,
            "source_policy": f"development_modal_source:{info.reference_source}",
        },
        "market": market_out(result.market),
        "warnings": result.warnings,
        "disclaimer": DISCLAIMER,
        "model": {"model_id": info.model_id, "readiness": info.readiness},
    }


def model_info_out(info: ModelInfo) -> dict[str, Any]:
    return {
        "model_id": info.model_id,
        "family": info.family,
        "feature_set": info.feature_set,
        "target_transform": info.target_transform,
        "trained_until": iso(info.trained_until),
        "test_metrics": {
            "mae": _money(info.test_mae), "median_ae": _money(info.test_median_ae),
            "r2": None if info.test_r2 is None else round(info.test_r2, 3),
        },
        "readiness": info.readiness,
        "reference_source": info.reference_source,
        "interval_coverage": info.interval_coverage,
        "typical_area_range": {"low": info.typical_area_range[0], "high": info.typical_area_range[1]},
        "reliable_price_range": {"low": _money(info.reliable_price_range[0]), "high": _money(info.reliable_price_range[1])},
    }
