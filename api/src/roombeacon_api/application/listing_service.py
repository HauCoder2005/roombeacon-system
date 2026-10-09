"""Listing use cases: search, detail with market comparison and model valuation, price history."""

from __future__ import annotations

from dataclasses import dataclass
import logging

from ..domain.errors import DependencyUnavailableError, InvalidParameterError, NotFoundError
from ..domain.models import IMAGE_CONTENT_TYPES, ImageObject, ImageRef, ListingCard, ModelInput, PricePoint
from .pagination import Page, PageRequest
from .ports import HistoryRepository, ImageStore, ListingRepository, LocationRepository, PriceModel
from .sorting import SortSpec


logger = logging.getLogger(__name__)
INTENTS = frozenset({"RENT", "TRANSFER", "SALE", "UNKNOWN", "ANY"})
LISTING_SORT_FIELDS = frozenset({"last_observed_at", "price", "area"})
# |asking - estimate| / estimate within this band reads as "near the estimate".
VALUATION_BAND_PCT = 10.0


@dataclass(frozen=True)
class ListingFilters:
    district_id: str | None = None
    ward_id: str | None = None
    q: str = ""
    price_min: int | None = None
    price_max: int | None = None
    area_min: float | None = None
    area_max: float | None = None
    intent: str = "RENT"
    exclude_duplicates: bool = True

    def __post_init__(self) -> None:
        for name in ("price_min", "price_max", "area_min", "area_max"):
            value = getattr(self, name)
            if value is not None and value < 0:
                raise InvalidParameterError(name, "out_of_range", f"{name} must be >= 0")
        if self.price_min is not None and self.price_max is not None and self.price_min > self.price_max:
            raise InvalidParameterError("price_min", "invalid_range", "price_min must be <= price_max")
        if self.area_min is not None and self.area_max is not None and self.area_min > self.area_max:
            raise InvalidParameterError("area_min", "invalid_range", "area_min must be <= area_max")
        if self.intent not in INTENTS:
            raise InvalidParameterError("intent", "not_allowed", f"intent must be one of: {', '.join(sorted(INTENTS))}")


@dataclass(frozen=True)
class Valuation:
    estimate: float
    delta_pct: float
    label: str


@dataclass(frozen=True)
class MarketComparison:
    scope: str
    name: str
    median: float | None
    p25: float | None
    p75: float | None
    listing_count: int
    position: str | None


PREVIEW_IMAGES = 4


@dataclass(frozen=True)
class ImageSummary:
    count: int
    cover_position: int | None
    preview_positions: tuple[int, ...] = ()


@dataclass(frozen=True)
class ListingDetail:
    listing: ListingCard
    valuation: Valuation | None
    market: MarketComparison | None


class ListingService:
    def __init__(
        self,
        listings: ListingRepository,
        history: HistoryRepository,
        locations: LocationRepository,
        price_model: PriceModel,
        images: ImageStore | None = None,
    ) -> None:
        self._listings = listings
        self._history = history
        self._locations = locations
        self._model = price_model
        self._images = images

    @property
    def images_enabled(self) -> bool:
        return self._images is not None

    def image_summaries(self, cards: list[ListingCard]) -> dict[str, ImageSummary] | None:
        """Image count and cover per card; None when images are off or storage is down."""
        if self._images is None:
            return None
        try:
            out = {}
            for card in cards:
                refs = self._refs(card)
                out[card.id] = ImageSummary(
                    len(refs),
                    refs[0].position if refs else None,
                    tuple(r.position for r in refs[:PREVIEW_IMAGES]),
                )
            return out
        except DependencyUnavailableError:
            logger.warning("image storage unavailable; listings served without images")
            return None

    def images(self, listing_id: str) -> list[ImageRef]:
        self._require_images()
        return self._refs(self._require(listing_id))

    def image(self, listing_id: str, position: int) -> ImageObject:
        self._require_images()
        ref = next((r for r in self._refs(self._require(listing_id)) if r.position == position), None)
        image = self._images.get_image(ref.key) if ref else None
        if image is None or image.content_type not in IMAGE_CONTENT_TYPES:
            raise NotFoundError("image", str(position))
        return image

    def _require_images(self) -> None:
        if self._images is None:
            raise NotFoundError("image", "disabled")

    def _refs(self, card: ListingCard) -> list[ImageRef]:
        if not card.source or not card.source_listing_id:
            return []
        return self._images.list_images(card.source, card.source_listing_id)

    def search(self, filters: ListingFilters, sort: SortSpec, page: PageRequest) -> tuple[Page[ListingCard], dict[str, Valuation]]:
        result = self._listings.search(filters, sort, page)
        return result, self._valuations(result.items)

    def get(self, listing_id: str) -> ListingDetail:
        card = self._require(listing_id)
        return ListingDetail(card, self._valuations([card]).get(card.id), self._market(card))

    def price_history(self, listing_id: str, page: PageRequest) -> Page[PricePoint]:
        self._require(listing_id)
        return self._history.price_history(listing_id, page)

    def _require(self, listing_id: str) -> ListingCard:
        card = self._listings.get(listing_id)
        if card is None:
            raise NotFoundError("listing", listing_id)
        return card

    def _valuations(self, cards: list[ListingCard]) -> dict[str, Valuation]:
        """Model estimate per listing (own source). A model outage degrades to no valuation."""
        eligible = [c for c in cards if c.price_vnd and c.area_m2 and c.area_m2 > 0 and c.district]
        if not eligible:
            return {}
        try:
            predictions = self._model.predict(
                [ModelInput(c.area_m2, c.district, c.ward, c.source) for c in eligible]
            )
        except DependencyUnavailableError:
            logger.warning("price model unavailable; listings served without valuation")
            return {}
        out = {}
        for card, prediction in zip(eligible, predictions):
            if prediction.value <= 0:
                continue
            delta = round((card.price_vnd - prediction.value) / prediction.value * 100, 1)
            label = (
                "BELOW_ESTIMATE" if delta < -VALUATION_BAND_PCT
                else "ABOVE_ESTIMATE" if delta > VALUATION_BAND_PCT
                else "NEAR_ESTIMATE"
            )
            out[card.id] = Valuation(prediction.value, delta, label)
        return out

    def _market(self, card: ListingCard) -> MarketComparison | None:
        try:
            if card.ward_id:
                ward = self._locations.get_ward(card.ward_id)
                if ward is not None:
                    return compare_with_market("ward", ward.name, ward.price, ward.listing_count, card.price_vnd)
            if card.district_id:
                district = self._locations.get_district(card.district_id)
                if district is not None:
                    return compare_with_market("district", district.name, district.price, district.listing_count, card.price_vnd)
        except DependencyUnavailableError:
            logger.warning("warehouse unavailable; listing served without market comparison")
        return None


def compare_with_market(scope, name, price, listing_count, asking) -> MarketComparison:
    """Where an asking price (or estimate) sits within a location's p25-p75 band."""
    position = None
    if asking is not None and price.p25 is not None and price.p75 is not None:
        position = "BELOW_P25" if asking < price.p25 else "ABOVE_P75" if asking > price.p75 else "WITHIN_P25_P75"
    return MarketComparison(scope, name, price.median, price.p25, price.p75, listing_count, position)
