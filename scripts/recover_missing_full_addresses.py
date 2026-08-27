#!/usr/bin/env python3
"""Queue bounded detail recovery for latest listings missing a full address.

The command preserves post identity and raw history: it only adds eligible
existing listings to the normal deferred-detail queue. It does not fetch pages,
write MySQL, bypass source policy, or run detail work ahead of discovery.
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
from typing import Iterable

from sqlalchemy import text

from roombeacon_crawler.enums.crawl_target_type import CrawlTargetType
from roombeacon_crawler.infrastructure.mysql.connection import MySQLConnectionFactory
from roombeacon_crawler.models.deferred_detail_item import DeferredDetailItem
from roombeacon_crawler.repositories.local_deferred_detail_repository import (
    LocalDeferredDetailRepository,
)
from roombeacon_crawler.sources.registry import SourceRegistry


LATEST_MISSING_QUERY = text(
    """
    WITH latest AS (
        SELECT id, rental_post_id,
               ROW_NUMBER() OVER (
                   PARTITION BY rental_post_id
                   ORDER BY observed_at DESC, id DESC
               ) AS rn
        FROM rental_post_versions
    )
    SELECT pl.code AS source, p.platform_post_id, p.url, p.title_raw
    FROM rental_posts p
    JOIN platforms pl ON pl.id = p.platform_id
    JOIN latest l ON l.rental_post_id = p.id AND l.rn = 1
    WHERE NOT EXISTS (
        SELECT 1
        FROM post_addresses a
        WHERE a.rental_post_id = p.id
          AND a.full_address_text IS NOT NULL
          AND TRIM(a.full_address_text) <> ''
    )
    ORDER BY p.last_observed_at DESC, p.id DESC
    """
)


def select_recovery_items(
    missing_listings: Iterable,
    *,
    registry,
    repository,
    target_id: str,
    limit: int,
):
    """Return eligible stable-identity queue items plus aggregate skip reasons."""
    queued_at = datetime.now(timezone.utc).isoformat()
    selected_details: list[DeferredDetailItem] = []
    skip_reasons: Counter[str] = Counter()
    deferred_state_by_source: dict[str, dict] = {}

    for missing_listing in missing_listings:
        source = str(missing_listing.source)
        if len(selected_details) >= limit:
            skip_reasons["LIMIT_REACHED"] += 1
            continue
        try:
            adapter = registry.get(source)()
        except KeyError:
            skip_reasons["SOURCE_UNREGISTERED"] += 1
            continue
        if not adapter.CAPABILITIES.detail_fetch_supported:
            skip_reasons["DETAIL_UNSUPPORTED"] += 1
            continue
        detail_url = str(missing_listing.url or "").strip()
        if (
            not detail_url
            or adapter.classify_url(detail_url) is not CrawlTargetType.DETAIL_PAGE
        ):
            skip_reasons["INVALID_OR_NON_LISTING_URL"] += 1
            continue

        source_state = deferred_state_by_source.setdefault(
            source, repository._load(source, target_id)
        )
        existing_detail = source_state.get(str(missing_listing.platform_post_id))
        if existing_detail and existing_detail.get("status") == "PENDING":
            skip_reasons["ALREADY_PENDING"] += 1
            continue
        if existing_detail and existing_detail.get("status") == "TERMINAL_FAILED":
            skip_reasons["TERMINAL"] += 1
            continue

        selected_details.append(
            DeferredDetailItem(
                source=source,
                platform_post_id=str(missing_listing.platform_post_id),
                detail_url=detail_url,
                origin_run_id="targeted_address_recovery",
                first_deferred_at=queued_at,
                reason="LATEST_FULL_ADDRESS_MISSING",
                card_title=missing_listing.title_raw,
            )
        )
    return selected_details, skip_reasons


def summarize_selection(
    missing_listings,
    selected_details,
    repository,
    target_id: str,
) -> dict[str, dict]:
    """Build source-level aggregate counts without exposing identities or URLs."""
    selected_counts = Counter(detail.source for detail in selected_details)
    missing_counts = Counter(str(listing.source) for listing in missing_listings)
    pending_counts: Counter[str] = Counter()
    for source in missing_counts:
        deferred_state = repository._load(source, target_id)
        pending_counts[source] = sum(
            1
            for pending_detail in deferred_state.values()
            if pending_detail.get("status") == "PENDING"
        )
    return {
        source: {
            "missing": missing_counts[source],
            "selected": selected_counts[source],
            "queue_pending_total": pending_counts[source],
        }
        for source in sorted(missing_counts)
    }


def parse_args() -> argparse.Namespace:
    """Parse bounded recovery options without reading runtime configuration."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--target-id", default="hcm_phongtro")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if args.limit < 1:
        parser.error("--limit must be positive")
    return args


def load_missing_listings():
    """Read current listings that have no confirmed full address."""
    with MySQLConnectionFactory.get_engine().connect() as connection:
        return connection.execute(LATEST_MISSING_QUERY).fetchall()


def enqueue_recovery_details(
    selected_details: list[DeferredDetailItem],
    *,
    repository,
    target_id: str,
) -> int:
    """Persist selected recovery work through the normal deferred queue."""
    details_by_source: dict[str, list[DeferredDetailItem]] = {}
    for pending_detail in selected_details:
        details_by_source.setdefault(pending_detail.source, []).append(pending_detail)
    return sum(
        repository.enqueue(source, target_id, pending_details)
        for source, pending_details in details_by_source.items()
    )


def main() -> int:
    args = parse_args()
    missing_listings = load_missing_listings()
    repository = LocalDeferredDetailRepository()
    selected_details, skip_reasons = select_recovery_items(
        missing_listings,
        registry=SourceRegistry(),
        repository=repository,
        target_id=args.target_id,
        limit=args.limit,
    )
    queued_count = (
        enqueue_recovery_details(
            selected_details,
            repository=repository,
            target_id=args.target_id,
        )
        if args.apply
        else 0
    )

    print(
        {
            "mode": "APPLY" if args.apply else "DRY_RUN",
            "missing_rows": len(missing_listings),
            "eligible_selected": len(selected_details),
            "queued": queued_count,
            "skipped": dict(sorted(skip_reasons.items())),
            "identities_changed": 0,
            "per_source": summarize_selection(
                missing_listings,
                selected_details,
                repository,
                args.target_id,
            ),
        }
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
