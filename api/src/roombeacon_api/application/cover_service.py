"""Cover images for district and ward cards.

A location's cover is the first image of its most recently observed searchable
listing (TP.HCM, SUPPORTED price, not a possible duplicate) that has photos in
object storage. Nothing is invented: no photo, no cover.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging

from ..domain.errors import DependencyUnavailableError
from .ports import ImageStore, ListingRepository


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CoverImage:
    listing_id: str
    position: int


class CoverService:
    def __init__(self, listings: ListingRepository, images: ImageStore) -> None:
        self._listings = listings
        self._images = images

    def covers(self, level: str, location_ids: list[str]) -> dict[str, CoverImage]:
        if not location_ids:
            return {}
        try:
            pairs = self._images.listings_with_images()
            chosen = self._listings.latest_with_images(pairs, level, location_ids)
            out = {}
            for location_id, listing_id in chosen.items():
                card = self._listings.get(listing_id)
                if card is None or not card.source_listing_id:
                    continue
                refs = self._images.list_images(card.source, card.source_listing_id)
                if refs:
                    out[location_id] = CoverImage(listing_id, refs[0].position)
            return out
        except DependencyUnavailableError:
            logger.warning("cover images unavailable; location cards served without covers")
            return {}
