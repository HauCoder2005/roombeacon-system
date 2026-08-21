from roombeacon_crawler.domain.errors.domain_error import (
    AnalyticsError,
    DatabaseConnectionError,
    DomainError,
    DuckDBAttachError,
    FetchError,
    ObservationConflictError,
    ParseError,
    PersistenceError,
    RobotsDeniedError,
    SourceAccessError,
)

__all__ = [
    "DomainError",
    "SourceAccessError",
    "RobotsDeniedError",
    "FetchError",
    "ParseError",
    "PersistenceError",
    "DatabaseConnectionError",
    "ObservationConflictError",
    "AnalyticsError",
    "DuckDBAttachError",
]
