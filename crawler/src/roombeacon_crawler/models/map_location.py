from dataclasses import dataclass

@dataclass
class MapLocation:
    """Independent embedded map coordinates captured from source details."""
    provider: str
    map_url_raw: str
    latitude: float | None = None
    longitude: float | None = None
    query_raw: str | None = None
