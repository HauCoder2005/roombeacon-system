from roombeacon_crawler.sources.base import BaseSourceAdapter
from roombeacon_crawler.sources.registry import SourceRegistry, source_registry


class SourceResolver:
    """Facade phân giải Source Adapter thông qua central SourceRegistry."""

    @classmethod
    def get_supported_sources(cls) -> list[str]:
        return source_registry.get_supported_sources()

    @classmethod
    def is_supported(cls, url: str) -> bool:
        return source_registry.is_supported(url)

    @classmethod
    def resolve_source_name(cls, url: str) -> str | None:
        return source_registry.resolve_source_name(url)

    @classmethod
    def resolve_adapter(
        cls,
        url: str,
        request_delay_seconds: float = 1.5,
        max_concurrency: int = 1,
    ) -> BaseSourceAdapter:
        return source_registry.resolve(
            url=url,
            request_delay_seconds=request_delay_seconds,
            max_concurrency=max_concurrency,
        )

    @classmethod
    def resolve(
        cls,
        url: str,
        request_delay_seconds: float = 1.5,
        max_concurrency: int = 1,
    ) -> BaseSourceAdapter:
        """Alias tương thích cho resolve_adapter."""
        return cls.resolve_adapter(
            url=url,
            request_delay_seconds=request_delay_seconds,
            max_concurrency=max_concurrency,
        )
