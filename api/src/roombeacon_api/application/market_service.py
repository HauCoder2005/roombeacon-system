"""Market summary and daily series."""

from __future__ import annotations

from datetime import date

from ..domain.errors import InvalidParameterError, NotFoundError
from ..domain.models import DistrictCard, MarketDay, MarketSummary
from .ports import LocationRepository, MarketRepository


MAX_DAILY_SPAN_DAYS = 92


class MarketService:
    def __init__(self, market: MarketRepository, locations: LocationRepository) -> None:
        self._market = market
        self._locations = locations

    def summary(self, district_id: str | None) -> tuple[MarketSummary, DistrictCard | None]:
        district = self._district(district_id)
        return self._market.summary(district_id), district

    def daily(self, district_id: str | None, date_from: date | None, date_to: date | None) -> list[MarketDay]:
        if date_from and date_to:
            if date_from > date_to:
                raise InvalidParameterError("date_from", "invalid_range", "date_from must be <= date_to")
            if (date_to - date_from).days > MAX_DAILY_SPAN_DAYS:
                raise InvalidParameterError("date_to", "window_too_wide", f"at most {MAX_DAILY_SPAN_DAYS} days per request")
        self._district(district_id)
        return self._market.daily(district_id, date_from, date_to)

    def _district(self, district_id: str | None) -> DistrictCard | None:
        if not district_id:
            return None
        district = self._locations.get_district(district_id)
        if district is None:
            raise NotFoundError("district", district_id)
        return district
