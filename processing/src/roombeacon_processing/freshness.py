"""Listing freshness: how old is each listing, from the source's own posted date?

Sources keep serving posts that are years old. Bronze keeps the posted-date
text exactly as the source showed it (``posted_at_raw``) on every observation.
Relative texts ("3 ngày trước") are interpreted against THAT observation's
time, absolute dates as written. A listing's posted date is the earliest
plausible evidence across its observations (a later "Hôm nay" bump does not
make an old post new). Nothing is guessed: no evidence -> UNKNOWN.

Output: one row per rental_post_id in a Parquet dataset beside Silver; the
Silver contract itself is unchanged.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
import unicodedata

import duckdb
import pandas as pd

from analytics.bronze.snapshot import verify_bronze_observations


DATASET = "listing_freshness"
DEFAULT_STALE_AFTER_DAYS = 90
SCHEMA_VERSION = "1.0.0"
EARLIEST_PLAUSIBLE = datetime(2000, 1, 1)
FUTURE_TOLERANCE = timedelta(days=1)
UNIT_DELTAS = {
    "phút": timedelta(minutes=1),
    "giờ": timedelta(hours=1),
    "ngày": timedelta(days=1),
    "tuần": timedelta(days=7),
    "tháng": timedelta(days=30),
    "năm": timedelta(days=365),
}
RELATIVE = re.compile(r"(\d{1,4})\s*(phút|giờ|ngày|tuần|tháng|năm)\s*trước")
DMY = re.compile(r"(?<!\d)(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})(?!\d)")
YMD = re.compile(r"(?<!\d)(\d{4})-(\d{1,2})-(\d{1,2})(?!\d)")
STATUS_RANK = {"ABSOLUTE": 0, "RELATIVE": 1, "IMPLAUSIBLE": 2, "UNPARSED": 3, "MISSING": 4}


class FreshnessError(RuntimeError):
    """Raised when freshness cannot be built from the given snapshot."""


@dataclass(frozen=True)
class FreshnessResult:
    snapshot_id: str
    output_dir: str
    row_count: int
    stale_after_days: int
    freshness_counts: dict[str, int]

    def to_dict(self) -> dict:
        return asdict(self)


def interpret_posted_at(raw: object, observed_at: datetime) -> tuple[datetime | None, str]:
    """(posted_at, status) with status ABSOLUTE | RELATIVE | UNPARSED | IMPLAUSIBLE | MISSING."""
    if raw is None or (isinstance(raw, float) and raw != raw):
        return None, "MISSING"
    text = unicodedata.normalize("NFC", str(raw)).strip().casefold()
    if not text:
        return None, "MISSING"
    observed = pd.Timestamp(observed_at).to_pydatetime().replace(tzinfo=None)
    posted, status = None, "UNPARSED"
    if "vừa xong" in text or "hôm nay" in text:
        posted, status = observed, "RELATIVE"
    elif "hôm qua" in text:
        posted, status = observed - timedelta(days=1), "RELATIVE"
    elif match := RELATIVE.search(text):
        posted, status = observed - int(match.group(1)) * UNIT_DELTAS[match.group(2)], "RELATIVE"
    else:
        for pattern, order in ((DMY, (3, 2, 1)), (YMD, (1, 2, 3))):
            match = pattern.search(text)
            if match:
                year, month, day = (int(match.group(i)) for i in order)
                try:
                    posted, status = datetime(year, month, day), "ABSOLUTE"
                except ValueError:
                    return None, "UNPARSED"
                break
    if posted is None:
        return None, status
    if posted > observed + FUTURE_TOLERANCE or posted < EARLIEST_PLAUSIBLE:
        return None, "IMPLAUSIBLE"
    return posted, status


def build_listing_freshness(observations: pd.DataFrame, stale_after_days: int = DEFAULT_STALE_AFTER_DAYS) -> pd.DataFrame:
    frame = observations.sort_values(["rental_post_id", "observed_at", "observation_id"]).copy()
    interpreted = [interpret_posted_at(raw, seen) for raw, seen in zip(frame["posted_at_raw"], frame["observed_at"])]
    frame["posted_at"] = pd.to_datetime([p for p, _ in interpreted])
    frame["posted_at_status"] = [s for _, s in interpreted]
    frame["_rank"] = frame["posted_at_status"].map(STATUS_RANK)

    grouped = frame.groupby("rental_post_id", sort=True)
    out = pd.DataFrame(
        {
            "posted_at": grouped["posted_at"].min(),
            "posted_at_status": grouped["_rank"].min().map({v: k for k, v in STATUS_RANK.items()}),
            "posted_at_raw_latest": grouped["posted_at_raw"].agg(lambda s: s.dropna().iloc[-1] if s.notna().any() else None),
            "property_type_raw": grouped["property_type_raw"].agg(lambda s: s.dropna().iloc[-1] if s.notna().any() else None),
            "first_observed_at": grouped["observed_at"].min(),
            "last_observed_at": grouped["observed_at"].max(),
        }
    )
    age = (out["last_observed_at"] - out["posted_at"]).dt.days
    out["listing_age_days"] = age.astype("Int64")
    out["freshness_status"] = "UNKNOWN"
    out.loc[age.notna() & age.le(stale_after_days), "freshness_status"] = "FRESH"
    out.loc[age.notna() & age.gt(stale_after_days), "freshness_status"] = "STALE"
    out["stale_after_days"] = int(stale_after_days)
    return out.reset_index()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def publish_listing_freshness(
    snapshot_dir: str | Path,
    output_dir: str | Path,
    stale_after_days: int = DEFAULT_STALE_AFTER_DAYS,
) -> FreshnessResult:
    if not 1 <= int(stale_after_days) <= 3650:
        raise FreshnessError("stale_after_days must be between 1 and 3650")
    observations_path, snapshot = verify_bronze_observations(Path(snapshot_dir))
    with duckdb.connect(":memory:") as connection:
        columns = {row[0] for row in connection.execute("DESCRIBE SELECT * FROM read_parquet(?)", [str(observations_path)]).fetchall()}
        if not {"posted_at_raw", "property_type_raw"} <= columns:
            raise FreshnessError("observations.parquet has no posted_at_raw; refresh the Bronze snapshot first")
        observations = connection.execute(
            "SELECT rental_post_id, observation_id, observed_at, posted_at_raw, property_type_raw FROM read_parquet(?)",
            [str(observations_path)],
        ).df()
    freshness = build_listing_freshness(observations, stale_after_days)

    output_dir = Path(output_dir)
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".tmp-", dir=output_dir))
    try:
        parquet = staging / f"{DATASET}.parquet"
        with duckdb.connect(":memory:") as connection:
            connection.register("freshness", freshness)
            connection.execute(f"COPY freshness TO '{str(parquet).replace(chr(39), chr(39) * 2)}' (FORMAT PARQUET, COMPRESSION ZSTD)")
        counts = {k: int(v) for k, v in freshness["freshness_status"].value_counts().sort_index().items()}
        metadata = {
            "dataset_name": DATASET,
            "schema_version": SCHEMA_VERSION,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source_snapshot_id": snapshot.get("snapshot_id"),
            "observations_sha256": _sha256(observations_path),
            "stale_after_days": int(stale_after_days),
            "row_count": int(len(freshness)),
            "freshness_counts": counts,
            "posted_at_status_counts": {k: int(v) for k, v in freshness["posted_at_status"].value_counts().sort_index().items()},
            "output_sha256": _sha256(parquet),
            "columns": list(freshness.columns),
        }
        (staging / f"{DATASET}.metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        # Data first, metadata last: readers trust the dataset only when metadata matches.
        os.replace(parquet, output_dir / parquet.name)
        os.replace(staging / f"{DATASET}.metadata.json", output_dir / f"{DATASET}.metadata.json")
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    return FreshnessResult(str(snapshot.get("snapshot_id")), str(output_dir), int(len(freshness)), int(stale_after_days), counts)


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Build listing freshness from the Bronze snapshot observations.")
    parser.add_argument("--snapshot-dir", type=Path, default=Path("data/bronze/snapshot"))
    parser.add_argument("--output-dir", type=Path, default=Path("data/freshness"))
    parser.add_argument("--stale-after-days", type=int, default=int(os.getenv("LISTING_STALE_AFTER_DAYS", DEFAULT_STALE_AFTER_DAYS)))
    args = parser.parse_args(argv)
    result = publish_listing_freshness(args.snapshot_dir, args.output_dir, args.stale_after_days)
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
