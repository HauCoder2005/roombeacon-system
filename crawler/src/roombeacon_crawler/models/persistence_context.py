from dataclasses import dataclass, field
from roombeacon_crawler.enums.ingestion_origin import IngestionOrigin

@dataclass(frozen=True)
class PersistenceContext:
    """Explicit persistence context to capture execution provenance."""
    ingestion_origin: IngestionOrigin = field(default=IngestionOrigin.UNKNOWN)
