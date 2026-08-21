import asyncio
from datetime import datetime, timezone
import json
import logging
from pathlib import Path

from roombeacon_crawler.application.persistence.persist_observations import PersistBronzeObservationsUseCase
from roombeacon_crawler.config.get_env import env
from roombeacon_crawler.models.crawl_plan import CrawlPlan
from roombeacon_crawler.enums.crawl_mode import CrawlMode
from roombeacon_crawler.enums.crawl_status import CrawlStatus
from roombeacon_crawler.infrastructure.mysql.connection import MySQLConnectionFactory
from roombeacon_crawler.infrastructure.mysql.repositories.observation_repository import MySQLObservationRepository
from roombeacon_crawler.infrastructure.mysql.repositories.platform_repository import MySQLPlatformRepository
from roombeacon_crawler.infrastructure.mysql.repositories.post_children_repository import MySQLPostChildrenRepository
from roombeacon_crawler.infrastructure.mysql.repositories.rental_post_repository import MySQLRentalPostRepository
from roombeacon_crawler.infrastructure.mysql.schema import ensure_mysql_schema
from roombeacon_crawler.infrastructure.mysql.transaction import MySQLTransactionManager
from roombeacon_crawler.mappers.bronze_observation_loader import BronzeObservationLoader
from roombeacon_crawler.pipeline.crawl_runner import CrawlRunner
from roombeacon_crawler.repositories.local_crawl_state_repository import LocalCrawlStateRepository
from analytics.duckdb.connection import DuckDBConnectionFactory
from analytics.duckdb.bootstrap import bootstrap_analytics
from sqlalchemy import text

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("RUNTIME_VERIFY")


async def run_pipeline_test():
    print("=" * 70)
    print("ROOMBEACON END-TO-END AUTOMATED RUNTIME PIPELINE VERIFICATION")
    print("=" * 70)

    # 0. Setup Schema
    ensure_mysql_schema()
    state_repo = LocalCrawlStateRepository()
    engine = MySQLConnectionFactory.get_engine()

    def get_db_counts():
        with engine.connect() as conn:
            p_cnt = conn.execute(text("SELECT COUNT(*) FROM platforms")).scalar()
            post_cnt = conn.execute(text("SELECT COUNT(*) FROM rental_posts")).scalar()
            ver_cnt = conn.execute(text("SELECT COUNT(*) FROM rental_post_versions")).scalar()
            price_cnt = conn.execute(text("SELECT COUNT(*) FROM post_prices")).scalar()
            loc_cnt = conn.execute(text("SELECT COUNT(*) FROM post_addresses")).scalar()
            dt_cnt = conn.execute(text("SELECT COUNT(*) FROM post_details")).scalar()
            img_cnt = conn.execute(text("SELECT COUNT(*) FROM post_images")).scalar()
            amen_cnt = conn.execute(text("SELECT COUNT(*) FROM post_amenities")).scalar()
            return {
                "platforms": p_cnt,
                "rental_posts": post_cnt,
                "rental_post_versions": ver_cnt,
                "post_prices": price_cnt,
                "post_addresses": loc_cnt,
                "post_details": dt_cnt,
                "post_images": img_cnt,
                "post_amenities": amen_cnt,
            }

    counts_before = get_db_counts()
    print(f"\n[MYSQL INITIAL STATE]: {counts_before}")

    # =========================================================================
    # 1. REAL NHATOT RUN 1
    # =========================================================================
    target_url = "https://www.nhatot.com/thue-phong-tro-tp-ho-chi-minh"
    plan1 = CrawlPlan(
        source="nhatot",
        target_id="hcm_phongtro",
        target_url=target_url,
        mode=CrawlMode.FORWARD_ONLY_INCREMENTAL,
        reason="AUTOMATED_INGESTION_RUN_1",
        planned_at=datetime.now(timezone.utc).isoformat(),
    )
    runner1 = CrawlRunner(target_url=target_url)
    records1, res1 = await runner1.run(plan=plan1, crawl_details=False)

    print("\n" + "-" * 70)
    print("STEP 1: NHATOT LIVE CRAWL RUN 1")
    print("-" * 70)
    print(f"Run 1 ID               : {res1.run_id}")
    print(f"Run 1 Crawl Status     : {res1.status.value}")
    print(f"Run 1 Stop Reason      : {res1.stop_reason}")
    print(f"Run 1 Records Seen     : {res1.records_seen}")
    print(f"Run 1 Records New      : {res1.records_new}")
    print(f"Run 1 Records Known    : {res1.records_known}")
    print(f"Run 1 Observations     : {res1.observations_written}")
    print(f"Run 1 Bronze Path      : {res1.bronze_path}")

    # Persist Run 1 into MySQL
    obs_list1 = BronzeObservationLoader.load_from_bronze_dir(res1.bronze_path, run_id=res1.run_id)
    tx_mgr = MySQLTransactionManager()
    use_case = PersistBronzeObservationsUseCase(
        platform_repo=MySQLPlatformRepository(),
        rental_post_repo=MySQLRentalPostRepository(),
        observation_repo=MySQLObservationRepository(),
        children_repo=MySQLPostChildrenRepository(),
        transaction_mgr=tx_mgr,
    )
    import_res1 = use_case.execute(obs_list1)
    print(f"Run 1 Posts Created    : {import_res1.posts_created}")
    print(f"Run 1 Posts Existing   : {import_res1.posts_existing}")
    print(f"Run 1 Obs Inserted     : {import_res1.observations_inserted}")
    print(f"Run 1 Tech Duplicates  : {import_res1.technical_duplicates}")

    # Update State Checkpoint
    state_repo.record_seen_listing_ids("nhatot", "hcm_phongtro", res1.observed_listing_ids)

    counts_after_run1 = get_db_counts()
    print(f"[MYSQL STATE AFTER RUN 1]: {counts_after_run1}")

    # =========================================================================
    # 2. REAL NHATOT RUN 2 (Different Run ID, Same Known Listings)
    # =========================================================================
    plan2 = CrawlPlan(
        source="nhatot",
        target_id="hcm_phongtro",
        target_url=target_url,
        mode=CrawlMode.FORWARD_ONLY_INCREMENTAL,
        reason="AUTOMATED_INGESTION_RUN_2",
        planned_at=datetime.now(timezone.utc).isoformat(),
    )
    runner2 = CrawlRunner(target_url=target_url)
    records2, res2 = await runner2.run(plan=plan2, crawl_details=False)

    print("\n" + "-" * 70)
    print("STEP 2: NHATOT LIVE CRAWL RUN 2 (Different Run ID, Known State)")
    print("-" * 70)
    print(f"Run 2 ID               : {res2.run_id}")
    print(f"Run 2 Records Seen     : {res2.records_seen}")
    print(f"Run 2 Records New      : {res2.records_new}")
    print(f"Run 2 Records Known    : {res2.records_known}")
    print(f"Run 2 Observations     : {res2.observations_written}")
    print(f"Run 2 Bronze Path      : {res2.bronze_path}")

    # Persist Run 2 into MySQL
    obs_list2 = BronzeObservationLoader.load_from_bronze_dir(res2.bronze_path, run_id=res2.run_id)
    import_res2 = use_case.execute(obs_list2)
    print(f"Run 2 Posts Created    : {import_res2.posts_created}")
    print(f"Run 2 Posts Existing   : {import_res2.posts_existing}")
    print(f"Run 2 Obs Inserted     : {import_res2.observations_inserted}")
    print(f"Run 2 Tech Duplicates  : {import_res2.technical_duplicates}")

    counts_after_run2 = get_db_counts()
    print(f"[MYSQL STATE AFTER RUN 2]: {counts_after_run2}")

    # Verify: rental_posts delta equals posts_created, rental_post_versions increased by observations_written
    posts_diff = counts_after_run2["rental_posts"] - counts_after_run1["rental_posts"]
    versions_diff = counts_after_run2["rental_post_versions"] - counts_after_run1["rental_post_versions"]
    print(f"\nVerification Run 2: rental_posts delta = {posts_diff} (Matches new posts created: {import_res2.posts_created})")
    print(f"Verification Run 2: rental_post_versions delta = {versions_diff} (Expected: {res2.observations_written})")
    assert posts_diff == import_res2.posts_created, f"rental_posts delta {posts_diff} != {import_res2.posts_created}!"
    assert versions_diff == res2.observations_written, f"rental_post_versions delta {versions_diff} != {res2.observations_written}!"

    # =========================================================================
    # 3. SAME RUN RETRY PROOF (Re-importing Run 2)
    # =========================================================================
    print("\n" + "-" * 70)
    print("STEP 3: SAME RUN RETRY PROOF (Re-importing Run 2)")
    print("-" * 70)
    import_res2_retry = use_case.execute(obs_list2)
    print(f"Retry Posts Created    : {import_res2_retry.posts_created} (Expected: 0)")
    print(f"Retry Posts Existing   : {import_res2_retry.posts_existing} (Expected: {len(obs_list2)})")
    print(f"Retry Obs Inserted     : {import_res2_retry.observations_inserted} (Expected: 0)")
    print(f"Retry Tech Duplicates  : {import_res2_retry.technical_duplicates} (Expected: {len(obs_list2)})")

    counts_after_retry = get_db_counts()
    print(f"[MYSQL STATE AFTER RETRY]: {counts_after_retry}")
    assert counts_after_retry["rental_posts"] == counts_after_run2["rental_posts"]
    assert counts_after_retry["rental_post_versions"] == counts_after_run2["rental_post_versions"]
    assert counts_after_retry["post_prices"] == counts_after_run2["post_prices"]
    assert counts_after_retry["post_addresses"] == counts_after_run2["post_addresses"]

    # =========================================================================
    # 4. DUCKDB ANALYTICS REFRESH & VERIFICATION
    # =========================================================================
    print("\n" + "-" * 70)
    print("STEP 4: DUCKDB ANALYTICS REFRESH & VERIFICATION")
    print("-" * 70)
    bootstrap_analytics()
    duck_conn = DuckDBConnectionFactory.get_connection()

    # Query 1: COUNT(*) FROM v_observations
    total_obs_duck = duck_conn.execute("SELECT COUNT(*) FROM v_observations").fetchone()[0]
    print(f"DuckDB v_observations count: {total_obs_duck}")
    print(f"MySQL rental_post_versions count: {counts_after_run2['rental_post_versions']}")
    assert total_obs_duck == counts_after_run2["rental_post_versions"], "DuckDB and MySQL observation counts do not match!"

    # Query 2: v_source_activity
    print("\n--- [DuckDB: v_source_activity] ---")
    df_act = duck_conn.execute("SELECT * FROM v_source_activity ORDER BY date DESC, platform").df()
    print(df_act.to_string(index=False))

    # Query 3: v_latest_posts
    print("\n--- [DuckDB: v_latest_posts (Top 5)] ---")
    df_latest = duck_conn.execute("SELECT source_code, rental_post_id, source_listing_id, title_raw, price_amount, location_raw, latest_observed_at FROM v_latest_posts LIMIT 5").df()
    print(df_latest.to_string(index=False))

    # Query 4: v_price_history
    print("\n--- [DuckDB: v_price_history (Sample)] ---")
    df_price = duck_conn.execute("SELECT source_code, rental_post_id, source_listing_id, run_id, observed_at, price_amount, previous_price, price_change FROM v_price_history LIMIT 10").df()
    print(df_price.to_string(index=False))

    # Query 5: v_content_changes
    print("\n--- [DuckDB: v_content_changes (Sample)] ---")
    df_changes = duck_conn.execute("SELECT source_code, rental_post_id, source_listing_id, run_id, observed_at, change_classification FROM v_content_changes LIMIT 10").df()
    print(df_changes.to_string(index=False))

    # Query 6: v_data_quality
    print("\n--- [DuckDB: v_data_quality] ---")
    df_dq = duck_conn.execute("SELECT * FROM v_data_quality").df()
    print(df_dq.to_string(index=False))

    # Sample latest observations in MySQL
    print("\n--- [MySQL: Sample Latest Observations] ---")
    with engine.connect() as conn:
        sample_rows = conn.execute(text(
            "SELECT v.id, pl.code, p.platform_post_id, v.crawl_run_id, v.observed_at, v.title_raw "
            "FROM rental_post_versions v "
            "JOIN rental_posts p ON v.rental_post_id = p.id "
            "JOIN platforms pl ON p.platform_id = pl.id "
            "ORDER BY v.id DESC LIMIT 3"
        )).fetchall()
        for row in sample_rows:
            print(dict(row._mapping))

    print("\n" + "=" * 70)
    print("ALL RUNTIME INTEGRATION CHECKS PASSED PERFECTLY!")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(run_pipeline_test())
