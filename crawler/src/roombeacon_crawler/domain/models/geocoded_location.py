from dataclasses import dataclass
from typing import Optional
from datetime import datetime

@dataclass
class GeocodedLocation:
    latitude: float
    longitude: float
    geocoded_address_text: Optional[str] = None
    geocoded_ward: Optional[str] = None
    geocoded_district: Optional[str] = None
    geocoded_city: Optional[str] = None
    geocode_provider: str = ""
    geocode_precision: Optional[str] = None
    geocoded_at: Optional[datetime] = None
