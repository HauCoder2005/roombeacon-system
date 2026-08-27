"""Resolve a target URL to its registered source-adapter instance."""

from roombeacon_crawler.sources.base import BaseSourceAdapter
from roombeacon_crawler.sources.registry import source_registry


class SourceResolver:
    """Facade phân giải Source Adapter thông qua central SourceRegistry."""

    @classmethod
    def get_supported_sources(cls) -> list[str]:
        """List source names currently registered by adapter discovery."""
        return source_registry.get_supported_sources()

    @classmethod
    def is_supported(cls, url: str) -> bool:
        """Return whether a registered adapter accepts the URL."""
        return source_registry.is_supported(url)

    @classmethod
    def resolve_source_name(cls, url: str) -> str | None:
        """Resolve only the stable source identifier for a URL."""
        return source_registry.resolve_source_name(url)

    @classmethod
    def resolve_adapter(
        cls,
        url: str,
        request_delay_seconds: float = 1.5,
        max_concurrency: int = 1,
    ) -> BaseSourceAdapter:
        """Construct the adapter matched to the URL and runtime limits."""
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
