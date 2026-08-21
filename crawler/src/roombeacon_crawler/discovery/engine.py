import asyncio
from datetime import datetime, timezone
import logging
from pathlib import Path

from roombeacon_crawler.discovery.base import SourceDiscoveryAdapter
from roombeacon_crawler.discovery.models import (
    DiscoveredUrl,
    DiscoveryArtifact,
    DiscoveryResult,
    DiscoveryStatus,
    DiscoveryType,
)
from roombeacon_crawler.discovery.sitemap.fetcher import SitemapFetcher
from roombeacon_crawler.discovery.sitemap.index_parser import SitemapIndexParser
from roombeacon_crawler.discovery.sitemap.parser import (
    SitemapDocumentType,
    SitemapUrlsetParser,
)
from roombeacon_crawler.discovery.sitemap.url_filter import DiscoveryUrlFilter
from roombeacon_crawler.discovery.storage import DiscoveryStorage

logger = logging.getLogger(__name__)


class SitemapDiscoveryEngine:
    """Engine chung điều phối tiến trình khám phá URL từ Sitemap XML cho các nguồn lớn.

    Trách nhiệm duy nhất: Điều phối tuần tự các thành phần chuyên biệt:
    1. Lấy entrypoints từ DiscoveryAdapter.
    2. Tải XML qua SitemapFetcher.
    3. Nhận diện <sitemapindex> vs <urlset>.
    4. Bóc tách sitemap con qua SitemapIndexParser hoặc URL qua SitemapUrlsetParser.
    5. Chuẩn hóa & khử trùng lặp qua DiscoveryUrlFilter (kèm bộ lọc nghiệp vụ của Adapter).
    6. Lưu artifact qua DiscoveryStorage.
    7. Trả về metadata DiscoveryResult gọn nhẹ.
    """

    def __init__(
        self,
        fetcher: SitemapFetcher | None = None,
        storage: DiscoveryStorage | None = None,
        storage_base_dir: str | Path | None = None,
    ) -> None:
        self.fetcher = fetcher or SitemapFetcher()
        self.storage = storage or DiscoveryStorage(base_dir=storage_base_dir)

    async def discover(
        self,
        adapter: SourceDiscoveryAdapter,
        run_id: str | None = None,
        max_depth: int = 3,
        max_sitemaps: int = 50,
    ) -> tuple[list[DiscoveredUrl], DiscoveryResult, DiscoveryArtifact]:
        """Thực thi chu trình khám phá URL hoàn chỉnh cho một DiscoveryAdapter."""
        now = datetime.now(timezone.utc)
        now_iso = now.isoformat()
        active_run_id = run_id or f"disc_{adapter.SOURCE_NAME}_{now.strftime('%Y%m%d_%H%M%S')}"

        logger.info("=" * 60)
        logger.info("BẮT ĐẦU SITEMAP DISCOVERY: %s (Run ID: %s)", adapter.SOURCE_NAME, active_run_id)
        logger.info("=" * 60)

        entrypoints = adapter.discover_entrypoints()
        if not entrypoints:
            logger.warning("DiscoveryAdapter %s không có entrypoints", adapter.SOURCE_NAME)
            res = DiscoveryResult(
                source=adapter.SOURCE_NAME,
                run_id=active_run_id,
                status=DiscoveryStatus.EMPTY,
                discovered_at=now_iso,
                count=0,
            )
            art = DiscoveryArtifact(
                source=adapter.SOURCE_NAME,
                run_id=active_run_id,
                discovered_at=now_iso,
                count=0,
                urls=[],
                artifact_path="",
            )
            return [], res, art

        sitemap_queue: list[tuple[str, int]] = [(ep, 1) for ep in entrypoints]
        processed_sitemaps: set[str] = set()
        seen_candidate_urls: set[str] = set()
        all_discovered: list[DiscoveredUrl] = []
        errors: list[str] = []

        # Phân giải discovery transport từ SourceCapabilities
        transport = getattr(adapter, "preferred_discovery_transport", None)
        if not transport:
            from roombeacon_crawler.sources.registry import source_registry
            reg_adapter = source_registry.get(adapter.SOURCE_NAME)
            if reg_adapter and hasattr(reg_adapter, "CAPABILITIES"):
                transport = reg_adapter.CAPABILITIES.preferred_discovery_transport
        transport = transport or FetchStrategy.HTTP

        while sitemap_queue and len(processed_sitemaps) < max_sitemaps:
            sitemap_url, depth = sitemap_queue.pop(0)
            if sitemap_url in processed_sitemaps:
                continue
            processed_sitemaps.add(sitemap_url)

            logger.info("Đang duyệt sitemap [Depth %d/%d | Transport: %s]: %s", depth, max_depth, transport.value, sitemap_url)
            resp = await self.fetcher.fetch(sitemap_url, transport=transport)
            if not resp.is_success or not resp.content:
                errors.append(f"Fetch failed ({resp.error}): {sitemap_url}")
                continue

            # 1. Thử parse dạng Sitemap Index
            index_entries = SitemapIndexParser.parse_index(resp.content)
            if index_entries:
                logger.info("Phát hiện Sitemap Index: %d child sitemaps trong %s", len(index_entries), sitemap_url)
                if depth < max_depth:
                    for child in index_entries:
                        if child.loc and child.loc not in processed_sitemaps:
                            sitemap_queue.append((child.loc, depth + 1))
                continue

            # 2. Thử parse dạng URL Set
            urlset_entries = SitemapUrlsetParser.parse_urlset(resp.content)
            if urlset_entries:
                raw_entries = [(e.loc, e.lastmod) for e in urlset_entries]
                filtered = DiscoveryUrlFilter.filter_and_deduplicate(
                    entries=raw_entries,
                    adapter=adapter,
                    discovered_from=sitemap_url,
                    discovery_type=DiscoveryType.SITEMAP_URLSET,
                    seen_urls=seen_candidate_urls,
                )
                all_discovered.extend(filtered)
                logger.info("Đã lọc được %d URL ứng viên hợp lệ từ %s", len(filtered), sitemap_url)

        # 3. Phân loại danh sách URL theo persistent seen state
        known_seen_urls = self.storage.get_seen_urls(adapter.SOURCE_NAME)
        new_urls = [u for u in all_discovered if u.url not in known_seen_urls]
        known_count = len(all_discovered) - len(new_urls)
        new_count = len(new_urls)

        logger.info(
            "DISCOVERY SUMMARY: Total=%d | Known=%d | New=%d",
            len(all_discovered),
            known_count,
            new_count,
        )

        # Cập nhật seen candidate URLs cho nguồn
        if new_urls:
            self.storage.record_seen_urls(
                adapter.SOURCE_NAME, [u.url for u in new_urls]
            )

        # 4. Lưu Discovery Artifact xuống file qua DiscoveryStorage
        artifact = self.storage.save_artifact(
            source=adapter.SOURCE_NAME,
            run_id=active_run_id,
            urls=all_discovered,
        )

        status = DiscoveryStatus.SUCCESS if all_discovered else (
            DiscoveryStatus.EMPTY if not errors else DiscoveryStatus.PARTIAL_SUCCESS
        )

        result = DiscoveryResult(
            source=adapter.SOURCE_NAME,
            run_id=active_run_id,
            status=status,
            discovered_at=now_iso,
            count=len(all_discovered),
            new_count=new_count,
            changed_count=0,
            artifact_path=artifact.artifact_path,
            error="; ".join(errors) if errors else None,
        )

        # Lưu DiscoveryTargetState
        from roombeacon_crawler.discovery.models import DiscoveryTargetState
        discovery_state = DiscoveryTargetState(
            source=adapter.SOURCE_NAME,
            last_discovery_at=now_iso,
            last_discovery_status=status.value if hasattr(status, "value") else str(status),
            last_discovered_count=len(all_discovered),
            last_new_count=new_count,
            last_changed_count=0,
            last_error="; ".join(errors) if errors else None,
        )
        self.storage.save_target_state(discovery_state)

        logger.info("=" * 60)
        logger.info(
            "HOÀN TẤT DISCOVERY: %s -> %d URLs (New: %d)",
            adapter.SOURCE_NAME,
            len(all_discovered),
            new_count,
        )
        logger.info("=" * 60)
        return all_discovered, result, artifact
