"""ClickHouse star schema: one declaration drives DDL, model columns and loads."""

from __future__ import annotations

from dataclasses import dataclass
import re


IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,62}$")


def quote_identifier(name: str) -> str:
    """Backtick-quote a validated identifier; identifiers cannot be bound."""
    if not IDENTIFIER.fullmatch(name):
        raise ValueError(f"Unsafe ClickHouse identifier: {name!r}")
    return f"`{name}`"


@dataclass(frozen=True)
class TableSpec:
    name: str
    columns: tuple[tuple[str, str], ...]
    order_by: tuple[str, ...]
    partition_by: str | None = None
    comment: str = ""

    @property
    def column_names(self) -> list[str]:
        return [name for name, _ in self.columns]

    def ddl(self, database: str, table: str | None = None) -> str:
        target = f"{quote_identifier(database)}.{quote_identifier(table or self.name)}"
        body = ",\n    ".join(f"{quote_identifier(n)} {t}" for n, t in self.columns)
        order = ", ".join(quote_identifier(c) for c in self.order_by)
        parts = [
            f"CREATE TABLE IF NOT EXISTS {target}\n(\n    {body}\n)",
            "ENGINE = MergeTree",
        ]
        if self.partition_by:
            parts.append(f"PARTITION BY {self.partition_by}")
        parts.append(f"ORDER BY ({order})")
        if self.comment:
            parts.append("COMMENT '" + self.comment.replace("\\", "\\\\").replace("'", "\\'") + "'")
        return "\n".join(parts)


STATUS = "LowCardinality(String)"
NULLABLE_STATUS = "LowCardinality(Nullable(String))"

TABLES: dict[str, TableSpec] = {
    "dim_date": TableSpec(
        "dim_date",
        (
            ("date_key", "UInt32"),
            ("calendar_date", "Date"),
            ("year", "UInt16"),
            ("quarter", "UInt8"),
            ("month", "UInt8"),
            ("day", "UInt8"),
            ("iso_week", "UInt8"),
            ("day_of_week", "UInt8"),
            ("is_weekend", "Bool"),
        ),
        order_by=("date_key",),
        comment="Calendar dimension; date_key = YYYYMMDD, day_of_week 1=Monday",
    ),
    "dim_source": TableSpec(
        "dim_source",
        (("source_key", "Int64"), ("source_code", STATUS)),
        order_by=("source_key",),
        comment="Crawled source websites",
    ),
    "dim_location": TableSpec(
        "dim_location",
        (
            ("location_key", "Int64"),
            ("location_level", STATUS),
            ("province", "Nullable(String)"),
            ("district", "Nullable(String)"),
            ("ward", "Nullable(String)"),
            ("parent_location_key", "Nullable(Int64)"),
        ),
        order_by=("location_key",),
        comment="Administrative units from Silver normalization (WARD, DISTRICT, UNKNOWN); no coordinates",
    ),
    "fact_listing_observation": TableSpec(
        "fact_listing_observation",
        (
            ("observation_id", "Int64"),
            ("rental_post_id", "Int64"),
            ("date_key", "UInt32"),
            ("observed_date", "Date"),
            ("observed_at", "DateTime64(6)"),
            ("source_key", "Int64"),
            ("location_key", "Int64"),
            ("district_location_key", "Int64"),
            ("crawl_run_id", "String"),
            ("version_seq", "UInt32"),
            ("is_content_change", "Bool"),
            ("is_price_change", "Bool"),
            ("price_amount", "Nullable(Float64)"),
            ("price_status", STATUS),
            ("area_value", "Nullable(Float64)"),
            ("area_status", STATUS),
            ("price_per_m2", "Nullable(Float64)"),
            ("listing_intent", NULLABLE_STATUS),
            ("rental_scope", NULLABLE_STATUS),
            ("is_market_eligible", "Bool"),
            ("has_trusted_coordinate", "Bool"),
            ("snapshot_id", "String"),
        ),
        order_by=("source_key", "rental_post_id", "observed_at", "observation_id"),
        partition_by="toYYYYMM(observed_date)",
        comment="One row per curated Bronze observation",
    ),
    "fact_listing_snapshot": TableSpec(
        "fact_listing_snapshot",
        (
            ("snapshot_id", "String"),
            ("as_of_date_key", "UInt32"),
            ("rental_post_id", "Int64"),
            ("source_key", "Int64"),
            ("location_key", "Int64"),
            ("district_location_key", "Int64"),
            ("first_observed_at", "DateTime64(6)"),
            ("last_observed_at", "DateTime64(6)"),
            ("active_days", "Int32"),
            ("observation_count", "UInt32"),
            ("content_version_count", "UInt32"),
            ("price_amount_clean", "Nullable(Float64)"),
            ("area_value_clean", "Nullable(Float64)"),
            ("listing_intent", NULLABLE_STATUS),
            ("rental_scope", NULLABLE_STATUS),
            ("price_model_suitability", NULLABLE_STATUS),
            ("row_quality_status", NULLABLE_STATUS),
            ("has_trusted_coordinate", "Bool"),
            ("duplicate_candidate_status", NULLABLE_STATUS),
        ),
        order_by=("source_key", "rental_post_id"),
        comment="Latest canonical Silver state per listing at the snapshot cutoff",
    ),
    "agg_market_daily": TableSpec(
        "agg_market_daily",
        (
            ("date_key", "UInt32"),
            ("market_date", "Date"),
            ("district_location_key", "Int64"),
            ("source_key", "Int64"),
            ("listings_observed", "UInt32"),
            ("new_listings", "UInt32"),
            ("observations", "UInt32"),
            ("content_changes", "UInt32"),
            ("price_changes", "UInt32"),
            ("market_eligible_listings", "UInt32"),
            ("median_price", "Nullable(Float64)"),
            ("p25_price", "Nullable(Float64)"),
            ("p75_price", "Nullable(Float64)"),
            ("median_price_per_m2", "Nullable(Float64)"),
            ("median_area", "Nullable(Float64)"),
            ("snapshot_id", "String"),
        ),
        order_by=("date_key", "district_location_key", "source_key"),
        partition_by="toYYYYMM(market_date)",
        comment="Gold mart: daily market state per district and source (last daily state per listing)",
    ),
}

# Dimensions first so a partially failed staging never exposes orphan facts.
LOAD_ORDER: tuple[str, ...] = tuple(TABLES)

LOAD_LOG = TableSpec(
    "etl_load_log",
    (
        ("load_id", "String"),
        ("snapshot_id", "String"),
        ("curated_metadata_sha256", "String"),
        ("silver_output_sha256", "String"),
        ("loaded_at", "DateTime64(3, 'UTC')"),
        ("table_row_counts", "String"),
        ("status", STATUS),
    ),
    order_by=("loaded_at", "load_id"),
    comment="One row per successful warehouse load",
)
