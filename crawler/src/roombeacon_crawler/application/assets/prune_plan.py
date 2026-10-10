"""List stored image objects that are not a listing's own photos.

Earlier reconciler runs stored every page image: logos, icons and related
listings' thumbnails. This job only writes a plan (one object key per line);
the crawler account cannot delete, so an operator removes the keys with the
MinIO admin client. Objects of listings missing from Bronze are never planned.

    python -m roombeacon_crawler.application.assets.prune_plan --out /data/state/assets/prune_keys.txt
"""

from __future__ import annotations

import argparse
import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable

from roombeacon_crawler.application.assets.listing_photos import ImageRow, select_post_photos

_KEY = re.compile(r"^(?P<source>[^/]+)/(?P<sid>.+)/img_\d{1,4}_(?P<hash>[0-9a-f]{8})\.(jpe?g|png|webp|gif)$")

# Images of every version of one post, by platform code and platform_post_id.
POST_IMAGES_SQL = """
    SELECT pi.rental_post_version_id, pi.position, pi.image_url
    FROM rental_posts p
    JOIN platforms pl ON pl.id = p.platform_id
    JOIN post_images pi ON pi.rental_post_id = p.id
    WHERE pl.code = %s AND p.platform_post_id = %s
    ORDER BY pi.rental_post_version_id, pi.position
"""


@dataclass
class PrunePlan:
    keys: list[str] = field(default_factory=list)
    per_source: dict[str, dict[str, int]] = field(default_factory=dict)


def _url_hash(url: str) -> str:
    return hashlib.md5(url.encode("utf-8")).hexdigest()[:8]


def plan_prune(
    object_keys: Iterable[str], versions_of: Callable[[str, str], list[list[ImageRow]] | None]
) -> PrunePlan:
    """Keys whose URL hash is not among the listing's selected photos."""
    plan = PrunePlan()
    by_listing: dict[tuple[str, str], list[tuple[str, str]]] = {}
    for key in object_keys:
        match = _KEY.match(key)
        if match:
            by_listing.setdefault((match["source"], match["sid"]), []).append((key, match["hash"]))

    for (source, sid), stored in sorted(by_listing.items()):
        counts = plan.per_source.setdefault(source, {"objects": 0, "prune": 0, "unknown_listing": 0})
        counts["objects"] += len(stored)
        versions = versions_of(source, sid)
        if versions is None:
            counts["unknown_listing"] += len(stored)
            continue
        own = {_url_hash(url) for _position, url in select_post_photos(source, sid, versions)}
        for key, url_hash in stored:
            if url_hash not in own:
                plan.keys.append(key)
                counts["prune"] += 1
    return plan


def main(argv: list[str] | None = None) -> int:
    from roombeacon_crawler.application.assets.asset_reconciler import AssetReconcilerService

    parser = argparse.ArgumentParser(description="Write the object keys of stored non-photo images (no deletes).")
    parser.add_argument("--out", required=True, type=Path, help="file to write, one object key per line")
    args = parser.parse_args(argv)

    service = AssetReconcilerService()
    s3 = service.get_s3_client()
    keys: list[str] = []
    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=service.bucket_name):
        keys.extend(item["Key"] for item in page.get("Contents", []))

    conn = service.get_mysql_connection()
    with conn:
        with conn.cursor() as cur:
            def versions_of(source: str, sid: str) -> list[list[ImageRow]] | None:
                cur.execute(POST_IMAGES_SQL, (source, sid))
                versions: dict[int, list[ImageRow]] = {}
                for r in cur.fetchall():
                    versions.setdefault(r["rental_post_version_id"], []).append((int(r["position"]), r["image_url"]))
                return list(versions.values()) or None

            plan = plan_prune(keys, versions_of)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("".join(f"{key}\n" for key in plan.keys), encoding="utf-8")
    for source, counts in sorted(plan.per_source.items()):
        print(f"{source:16} objects={counts['objects']:6} prune={counts['prune']:6} unknown_listing={counts['unknown_listing']}")
    print(f"total prune={len(plan.keys)} written to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
