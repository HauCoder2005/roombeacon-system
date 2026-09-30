"""Validate geographic coordinates for listing maps."""

import logging
import math

logger = logging.getLogger(__name__)

class LocationValidator:
    """Kiểm tra và chuẩn hóa toạ độ trước khi lưu."""

    @staticmethod
    def validate_coordinates(
        lat: float | None, lng: float | None, source_id: str = "unknown"
    ) -> tuple[float | None, float | None]:
        """
        Kiểm tra cặp toạ độ hợp lệ. 
        Nếu một trong hai bị thiếu, trả về (None, None).
        Nếu ngoài thế giới, trả về (None, None).
        KHÔNG silently swap nếu bị đảo ngược.
        """
        if (lat is not None and lng is None) or (lat is None and lng is not None):
            logger.warning("Partial coordinate pair detected for %s. Dropping.", source_id)
            return None, None

        if lat is None and lng is None:
            return None, None

        if not isinstance(lat, (int, float)) or not isinstance(lng, (int, float)):
            logger.warning("Non-numeric coordinates for %s.", source_id)
            return None, None

        if not math.isfinite(lat) or not math.isfinite(lng):
            logger.warning("Infinite/NaN coordinates for %s.", source_id)
            return None, None

        if lat == 0 and lng == 0:
            logger.warning("Null-island (0,0) coordinates for %s.", source_id)
            return None, None

        # World bounds
        if not (-90 <= lat <= 90) or not (-180 <= lng <= 180):
            logger.warning("Coordinates out of world bounds for %s: (%s, %s)", source_id, lat, lng)
            return None, None

        # Vietnam bounds check & swap detection
        # Vietnam envelope: Lat 8-24, Lng 102-110
        is_vn_lat = 8 <= lat <= 24
        is_vn_lng = 102 <= lng <= 110

        if not is_vn_lat or not is_vn_lng:
            # Check if swapped
            if 102 <= lat <= 110 and 8 <= lng <= 24:
                logger.warning("Coordinates appear swapped for %s: (%s, %s). Dropping.", source_id, lat, lng)
                return None, None

        return float(lat), float(lng)
