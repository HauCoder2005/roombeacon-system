from enum import Enum

class IngestionOrigin(str, Enum):
    """Explicit execution provenance for persisted observations."""
    LIVE_CRAWLER = "LIVE_CRAWLER"
    BRONZE_RECONCILER = "BRONZE_RECONCILER"
    UNKNOWN = "UNKNOWN"
