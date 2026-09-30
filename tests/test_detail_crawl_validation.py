"""Regression tests for detail-page validation at the pipeline boundary."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from roombeacon_crawler.enums.crawl_status import CrawlStatus
from roombeacon_crawler.enums.crawl_target_type import CrawlTargetType
from roombeacon_crawler.enums.fetch_strategy import FetchStrategy
from roombeacon_crawler.models.captured_response import CapturedResponse
from roombeacon_crawler.models.crawl_target import CrawlTarget
from roombeacon_crawler.models.listing_card_raw import ListingCardRaw
from roombeacon_crawler.models.listing_detail_raw import ListingDetailRaw
from roombeacon_crawler.pipeline.detail_crawl import DetailCrawlPipeline


def test_invalid_detail_is_rejected_before_bronze_mapping():
    """An empty detail parse must not be reported as a successful enrichment."""
    detail_url = "https://example.com/listing/123"
    invalid_detail = ListingDetailRaw(
        source="example",
        listing_id="123",
        detail_url=detail_url,
    )
    adapter = SimpleNamespace(
        detail_parser=SimpleNamespace(parse=Mock(return_value=invalid_detail))
    )
    response = CapturedResponse(
        request_url=detail_url,
        final_url=detail_url,
        status_code=200,
        html="<html></html>",
        headers={},
        fetch_strategy=FetchStrategy.HTTP,
    )
    metadata = SimpleNamespace(crawl_status=CrawlStatus.SUCCESS)
    fetch_coordinator = SimpleNamespace(
        fetch=AsyncMock(return_value=(response, CrawlStatus.SUCCESS, metadata))
    )
    robots_policy = SimpleNamespace(is_allowed=Mock(return_value=True))
    card = ListingCardRaw(
        source="example",
        listing_id="123",
        detail_url=detail_url,
        title_raw="Card title",
        price_raw="3 triệu/tháng",
        area_raw="25 m2",
        location_raw="Quận 1",
        posted_at_raw=None,
    )
    target = CrawlTarget(
        url=detail_url,
        source="example",
        target_type=CrawlTargetType.DETAIL_PAGE,
        listing_id="123",
    )
    pipeline = DetailCrawlPipeline(
        adapter=adapter,
        fetch_coordinator=fetch_coordinator,
        robots_policy=robots_policy,
    )

    bronze, detail, returned_metadata = asyncio.run(
        pipeline.execute(
            target=target,
            card=card,
            run_id="run-1",
        )
    )

    assert detail is None
    assert returned_metadata.crawl_status == CrawlStatus.PARSE_ERROR
    assert bronze is not None
    assert bronze.title_raw == "Card title"
    assert bronze.price_raw == "3 triệu/tháng"
