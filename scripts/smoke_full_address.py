"""Run controlled detail-page address smoke checks through crawler policies.

The command performs acquisition and parsing only. It does not write Bronze,
MySQL, checkpoint, deferred state, or Airflow state, and never prints raw URLs
or extracted address/contact values.
"""

import argparse
import asyncio
from dataclasses import dataclass

from roombeacon_crawler.enums.crawl_target_type import CrawlTargetType
from roombeacon_crawler.models.crawl_target import CrawlTarget
from roombeacon_crawler.pipeline.detail_crawl import DetailCrawlPipeline
from roombeacon_crawler.sources.resolver import SourceResolver


@dataclass(frozen=True)
class SmokeTarget:
    source: str
    url: str
    listing_id: str


def _looks_more_specific_than_district(value: str | None) -> bool:
    if not value:
        return False
    normalized = value.casefold()
    has_local_component = any(
        token in normalized
        for token in ("đường", "phường", "xã", "mặt tiền", "hẻm")
    )
    return has_local_component and "," in value


async def _check(target: SmokeTarget) -> tuple[str, bool, str]:
    adapter = SourceResolver.resolve(target.url)
    pipeline = DetailCrawlPipeline(adapter=adapter)
    crawl_target = CrawlTarget(
        url=target.url,
        source=target.source,
        target_type=CrawlTargetType.DETAIL_PAGE,
        listing_id=target.listing_id,
    )
    _bronze, detail, metadata = await pipeline.execute(
        target=crawl_target,
        card=None,
        run_id="address_smoke_no_persist",
    )
    address = detail.address_raw if detail else None
    ok = metadata.crawl_status.value == "success" and _looks_more_specific_than_district(address)
    return target.source, ok, metadata.crawl_status.value


async def _main(targets: list[SmokeTarget]) -> int:
    failures = 0
    for target in targets:
        source, ok, status = await _check(target)
        print(
            f"source={source} fetch_status={status} "
            f"full_address={'PASS' if ok else 'FAIL'}"
        )
        failures += int(not ok)
    return 1 if failures else 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--nhatrovn-url", required=True)
    parser.add_argument("--nhatrovn-id", required=True)
    parser.add_argument("--phongtro123-url", required=True)
    parser.add_argument("--phongtro123-id", required=True)
    parser.add_argument("--nhatot-url")
    parser.add_argument("--nhatot-id")
    args = parser.parse_args()
    targets = [
        SmokeTarget("nhatrovn", args.nhatrovn_url, args.nhatrovn_id),
        SmokeTarget("phongtro123", args.phongtro123_url, args.phongtro123_id),
    ]
    if bool(args.nhatot_url) != bool(args.nhatot_id):
        parser.error("--nhatot-url and --nhatot-id must be supplied together")
    if args.nhatot_url and args.nhatot_id:
        targets.append(SmokeTarget("nhatot", args.nhatot_url, args.nhatot_id))
    return asyncio.run(_main(targets))


if __name__ == "__main__":
    raise SystemExit(main())
