import urllib.request
import urllib.error
import json
import logging
import os
from urllib.parse import urlparse
from datetime import datetime, timezone
from roombeacon_crawler.domain.models.geocoded_location import GeocodedLocation

logger = logging.getLogger(__name__)

class NominatimReverseGeocoder:
    USER_AGENT = "RoomBeacon-Crawler-Analytics/1.0"
    BASE_URL = "https://nominatim.openstreetmap.org/reverse"

    def __init__(self, *, allow_public: bool | None = None):
        self.base_url = os.environ.get("GEOCODER_BASE_URL", self.BASE_URL)
        self.user_agent = os.environ.get("GEOCODER_USER_AGENT", self.USER_AGENT)
        if allow_public is None:
            allow_public = os.environ.get("GEOCODER_ALLOW_PUBLIC_NOMINATIM", "false").lower() == "true"
        self.enabled = urlparse(self.base_url).hostname != "nominatim.openstreetmap.org" or allow_public

    def reverse(self, latitude: float, longitude: float) -> GeocodedLocation | None:
        if not self.enabled:
            return None
        if not (-90 <= latitude <= 90) or not (-180 <= longitude <= 180):
            return None
        
        req = urllib.request.Request(
            f"{self.base_url}?format=json&addressdetails=1&lat={latitude}&lon={longitude}",
            headers={'User-Agent': self.user_agent}
        )
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read())
                
                if 'error' in data:
                    logger.warning("Nominatim returned error: %s", data['error'])
                    return None
                    
                address = data.get("address", {})
                
                # Extract address parts safely
                ward = address.get("suburb") or address.get("quarter")
                district = address.get("city_district") or address.get("county") or address.get("town")
                city = address.get("city") or address.get("state")
                
                # If they are totally empty but display_name exists
                display_name = data.get("display_name")
                if not isinstance(display_name, str) or not display_name.strip():
                    return None
                
                precision = data.get("type", "unknown")
                if any(address.get(key) for key in ("road", "pedestrian", "residential")):
                    precision = "house" if address.get("house_number") else "street"
                
                return GeocodedLocation(
                    latitude=latitude,
                    longitude=longitude,
                    geocoded_address_text=display_name,
                    geocoded_ward=ward,
                    geocoded_district=district,
                    geocoded_city=city,
                    geocode_provider="nominatim",
                    geocode_precision=precision,
                    geocoded_at=datetime.now(timezone.utc)
                )
        except urllib.error.URLError as e:
            logger.error("Reverse geocoding HTTP error: %s", e)
            return None
        except Exception as e:
            logger.error("Reverse geocoding error: %s", e)
            return None
