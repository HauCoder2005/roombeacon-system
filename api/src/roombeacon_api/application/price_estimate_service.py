"""Price estimate use case on the locked champion (no retraining, no reselection)."""

from __future__ import annotations

from dataclasses import dataclass

from ..domain.errors import InvalidParameterError, NotFoundError
from ..domain.models import DistrictCard, ModelInfo, ModelInput, PricePrediction, WardCard
from .listing_service import MarketComparison, compare_with_market
from .ports import LocationRepository, PriceModel


@dataclass(frozen=True)
class EstimateResult:
    prediction: PricePrediction
    area_m2: float
    district: DistrictCard
    ward: WardCard | None
    warnings: list[str]
    info: ModelInfo
    market: MarketComparison


class PriceEstimateService:
    def __init__(self, locations: LocationRepository, model: PriceModel) -> None:
        self._locations = locations
        self._model = model

    def model_info(self) -> ModelInfo:
        return self._model.info()

    def estimate(self, area_m2: float, district_id: str, ward_id: str | None) -> EstimateResult:
        district = self._locations.get_district(district_id)
        if district is None:
            raise NotFoundError("district", district_id)
        ward = None
        if ward_id:
            ward = self._locations.get_ward(ward_id)
            if ward is None:
                raise NotFoundError("ward", ward_id)
            if ward.district_id != district.id:
                raise InvalidParameterError("ward_id", "mismatch", "ward_id does not belong to district_id")

        info = self._model.info()
        prediction = self._model.predict([ModelInput(area_m2, district.name, ward.name if ward else None, None)])[0]

        warnings = [f"{feature}_unknown_to_model" for feature in prediction.unknown_features]
        low_area, high_area = info.typical_area_range
        if not low_area <= area_m2 <= high_area:
            warnings.append("area_outside_typical_range")
        low_price, high_price = info.reliable_price_range
        if prediction.value < low_price:
            warnings.append("low_price_segment_less_accurate")
        elif prediction.value > high_price:
            warnings.append("high_price_segment_less_accurate")
        place = ward or district
        market = compare_with_market(
            "ward" if ward else "district", place.name, place.price, place.listing_count, prediction.value
        )
        return EstimateResult(prediction, area_m2, district, ward, warnings, info, market)
