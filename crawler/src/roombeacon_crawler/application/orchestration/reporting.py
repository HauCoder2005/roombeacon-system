"""Aggregate task outputs into one operator-facing scheduled-run summary.

This module is deliberately Airflow-free. Runtime adapters are composed inside the
relevant use-case boundary until Phase 3 introduces explicit composition roots.
"""

import logging
from roombeacon_crawler.enums.crawl_mode import CrawlMode
from roombeacon_crawler.enums.crawl_status import CrawlStatus

logger = logging.getLogger(__name__)


def summarize_run(
    plans: list[dict] = None,
    qualifications: list[dict] = None,
    crawl_results: list[dict] = None,
    persistence_results: list[dict] = None,
    checkpoints: list[dict] = None,
    analytics_summary: dict = None,
    asset_summary: dict = None,
    **context,
) -> dict:
    """8. Tổng hợp số liệu thống kê toàn diện của toàn bộ fleet sau phiên cào."""
    plans = plans or []
    qualifications = qualifications or []
    crawl_results = crawl_results or []
    persistence_results = persistence_results or []
    checkpoints = checkpoints or []
    analytics_summary = analytics_summary or {}
    asset_summary = asset_summary or {}

    targets_due = len(plans)
    targets_deferred_cooldown = sum(1 for q in qualifications if q.get("qualification_status") == "COOLDOWN_ACTIVE")
    targets_executable = targets_due - targets_deferred_cooldown

    bootstrap_planned = sum(1 for p in plans if p.get("mode") == CrawlMode.BOOTSTRAP_FULL.value)
    bootstrap_continue_planned = sum(1 for p in plans if p.get("mode") == CrawlMode.BOOTSTRAP_CONTINUE.value)
    incremental_planned = sum(
        1
        for p in plans
        if p.get("mode") in (CrawlMode.INCREMENTAL.value, CrawlMode.FORWARD_ONLY_INCREMENTAL.value)
    )

    qualification_allowed = sum(1 for q in qualifications if q.get("qualification_status") == "READY")
    robots_denied = sum(1 for q in qualifications if q.get("qualification_status") == "DENIED_BY_ROBOTS")
    robots_unavailable = sum(1 for q in qualifications if q.get("qualification_status") == "CHECK_FAILED")

    crawl_success = sum(1 for r in crawl_results if r.get("crawl_status") == CrawlStatus.SUCCESS.value)
    access_challenge = sum(
        1
        for r in crawl_results
        if r.get("crawl_status") in (CrawlStatus.CLOUDFLARE_CHALLENGE.value, CrawlStatus.ACCESS_DENIED.value)
        or r.get("action") == "ACCESS_CHALLENGE"
    )
    technical_failure = sum(
        1
        for r in crawl_results
        if r.get("crawl_status")
        in (
            CrawlStatus.CONNECTION_ERROR.value,
            CrawlStatus.SERVER_ERROR.value,
            CrawlStatus.TIMEOUT.value,
            CrawlStatus.PARSE_ERROR.value,
        )
    )

    records_created = sum(r.get("records_created", 0) for r in crawl_results)
    observations_written = sum(r.get("observations_written", 0) for r in crawl_results)
    details_created = sum(r.get("details_success", 0) for r in crawl_results)

    mysql_posts_created = sum(p.get("posts_created", 0) for p in persistence_results)
    mysql_posts_existing = sum(p.get("posts_existing", 0) for p in persistence_results)
    mysql_obs_inserted = sum(p.get("observations_inserted", 0) for p in persistence_results)
    mysql_tech_duplicates = sum(p.get("technical_duplicates", 0) for p in persistence_results)

    target_states_persisted = sum(1 for c in checkpoints if c.get("target_state_persisted"))
    success_checkpoints_advanced = sum(1 for c in checkpoints if c.get("success_checkpoint_advanced"))
    health_states_updated = sum(1 for c in checkpoints if c.get("health_state_updated"))

    logger.info("=" * 60)
    logger.info("ROOMBEACON INGESTION SUMMARY")
    logger.info("=" * 60)
    logger.info("Targets due                  : %d", targets_due)
    logger.info("Targets executable           : %d", targets_executable)
    logger.info("Targets deferred cooldown    : %d", targets_deferred_cooldown)
    logger.info("Bootstrap planned            : %d", bootstrap_planned)
    logger.info("Bootstrap continue planned   : %d", bootstrap_continue_planned)
    logger.info("Incremental planned          : %d", incremental_planned)
    logger.info("Qualification allowed        : %d", qualification_allowed)
    logger.info("Robots denied                : %d", robots_denied)
    logger.info("Robots unavailable           : %d", robots_unavailable)
    logger.info("Crawl success                : %d", crawl_success)
    logger.info("Access challenge             : %d", access_challenge)
    logger.info("Technical failure            : %d", technical_failure)
    logger.info("Records created (new)        : %d", records_created)
    logger.info("Observations written (Bronze): %d", observations_written)
    logger.info("Details created              : %d", details_created)
    logger.info("-" * 60)
    logger.info("MYSQL PERSISTENCE SUMMARY:")
    logger.info("Posts Created                : %d", mysql_posts_created)
    logger.info("Posts Existing               : %d", mysql_posts_existing)
    logger.info("Observations Inserted        : %d", mysql_obs_inserted)
    logger.info("Technical Duplicates         : %d", mysql_tech_duplicates)
    logger.info("-" * 60)
    logger.info("CHECKPOINT & HEALTH:")
    logger.info("Target states persisted      : %d", target_states_persisted)
    logger.info("Success checkpoints advanced : %d", success_checkpoints_advanced)
    logger.info("Health states updated        : %d", health_states_updated)
    logger.info("=" * 60)
    logger.info("SOURCE COVERAGE & ACQUISITION SUMMARY:")
    for r in crawl_results:
        src = r.get("source", "unknown")
        recs = r.get("records_created", 0)
        obs_w = r.get("observations_written", 0)
        seen_cnt = r.get("records_seen", 0)
        new_cnt = r.get("records_new", 0)
        known_cnt = r.get("records_known", 0)
        changed_cnt = r.get("records_changed", 0)
        det_succ = r.get("details_success", 0)
        det_skip = r.get("detail_requests_skipped", 0)
        det_force = r.get("detail_requests_forced_by_change", 0)
        u_yield = r.get("unique_yield", 0.0)
        c_rate = r.get("change_rate", 0.0)
        b_start = r.get("bootstrap_start_page", 1)
        b_next = r.get("bootstrap_next_page")
        b_comp = r.get("bootstrap_completed", False)
        h_status = "COMPLETE" if b_comp else "IN_PROGRESS"

        b_path = r.get("bronze_path") or "NONE"
        p_res = next((p for p in persistence_results if p.get("source") == src), {})
        m_status = p_res.get("status", "NONE")
        m_p_created = p_res.get("posts_created", 0)
        m_p_exist = p_res.get("posts_existing", 0)
        m_obs_ins = p_res.get("observations_inserted", 0)
        m_dups = p_res.get("technical_duplicates", 0)

        det_req = r.get("detail_required", seen_cnt)
        immediate_requested = r.get("detail_requested", 0)
        immediate_succeeded = r.get("detail_succeeded", 0)
        immediate_failed = r.get("detail_failed", 0)
        total_detail_succeeded = r.get("details_success", immediate_succeeded)
        total_detail_failed = r.get("details_failed", immediate_failed)
        det_skip = r.get("detail_skipped", r.get("detail_requests_skipped", 0))

        skip_ttl = r.get("skipped_known_unchanged_ttl", 0)
        skip_nourl = r.get("skipped_no_detail_url", 0)
        skip_budget = r.get("skipped_request_budget", 0)
        skip_policy = r.get("skipped_source_policy", 0)
        skip_other = r.get("skipped_other", 0)

        def_before = r.get("deferred_backlog_before", 0)
        def_added = r.get("deferred_added", 0)
        def_att = r.get("deferred_attempted", 0)
        def_succ = r.get("deferred_succeeded", 0)
        def_fail = r.get("deferred_failed", 0)
        def_term = r.get("deferred_terminal", 0)
        def_rem = r.get("deferred_remaining", 0)
        total_detail_attempted = immediate_requested + def_att
        cov = r.get("detail_coverage", 0.0)
        light_only = r.get("lightweight_only_listings", 0)
        full_address_present = r.get("full_address_present", 0)
        full_address_missing = r.get("full_address_missing", 0)
        coarse_only_address = r.get("coarse_only_address", 0)
        detail_address_extracted = r.get("detail_address_extracted", 0)
        detail_address_parse_failed = r.get("detail_address_parse_failed", 0)

        logger.info("=" * 60)
        logger.info("ROOMBEACON ACQUISITION SUMMARY")
        logger.info("=" * 60)
        logger.info("Source                    : %s", src)
        logger.info("Candidates Seen           : %d", seen_cnt)
        logger.info("New Unique Posts          : %d", new_cnt)
        logger.info("Known Posts               : %d", known_cnt)
        logger.info("Changed Listings          : %d", changed_cnt)
        logger.info("------------------------------------------------------------")
        logger.info("Detail Required           : %d", det_req)
        logger.info("Detail Attempted (Total)  : %d", total_detail_attempted)
        logger.info("Detail Succeeded (Total)  : %d", total_detail_succeeded)
        logger.info("Detail Failed (Total)     : %d", total_detail_failed)
        logger.info("Immediate Requested       : %d", immediate_requested)
        logger.info("Immediate Succeeded       : %d", immediate_succeeded)
        logger.info("Immediate Failed          : %d", immediate_failed)
        logger.info("Page-card Detail Skipped  : %d", det_skip)
        logger.info("Full Address Present      : %d", full_address_present)
        logger.info("Full Address Missing      : %d", full_address_missing)
        logger.info("Coarse-only Address       : %d", coarse_only_address)
        logger.info("Detail Address Extracted  : %d", detail_address_extracted)
        logger.info("Detail Address Parse Fail : %d", detail_address_parse_failed)
        logger.info("------------------------------------------------------------")
        logger.info("Skip — TTL                : %d", skip_ttl)
        logger.info("Skip — No Detail URL      : %d", skip_nourl)
        logger.info("Skip — Request Budget     : %d", skip_budget)
        logger.info("Skip — Source Policy      : %d", skip_policy)
        logger.info("Skip — Other              : %d", skip_other)
        logger.info("------------------------------------------------------------")
        logger.info("Deferred Backlog Before   : %d", def_before)
        logger.info("Deferred Added            : %d", def_added)
        logger.info("Deferred Attempted        : %d", def_att)
        logger.info("Deferred Succeeded        : %d", def_succ)
        logger.info("Deferred Failed           : %d", def_fail)
        logger.info("Deferred Terminal         : %d", def_term)
        logger.info("Deferred Remaining        : %d", def_rem)
        logger.info("------------------------------------------------------------")
        logger.info("Detail Coverage           : %.1f%%", cov)
        logger.info("Lightweight-only Listings : %d", light_only)
        logger.info("------------------------------------------------------------")
        logger.info("Forced Detail Refresh     : %d", det_force)
        logger.info("Unique Yield              : %.1f%%", u_yield)
        logger.info("Change Rate               : %.1f%%", c_rate)
        logger.info("Observations Written      : %d", obs_w)
        logger.info("Historical Frontier Before: %d", b_start)
        logger.info("Historical Frontier After : %s", str(b_next) if b_next else "N/A")
        logger.info("Historical Status         : %s", h_status)
        logger.info("Bronze Path               : %s", b_path)
        logger.info("MySQL Status              : %s (Ins: %d, Dups: %d)", m_status, m_obs_ins, m_dups)
        logger.info("=" * 60)

    logger.info("=" * 60)
    logger.info("DuckDB")
    logger.info("  Refresh              : %s", analytics_summary.get("status", "UNKNOWN") if analytics_summary else "UNKNOWN")
    logger.info("-" * 60)
    logger.info("MINIO ASSET SYNC")
    logger.info("  Batch budget         : %d", asset_summary.get("batch_budget", 0))
    logger.info("  Selected             : %d", asset_summary.get("batch_used", 0))
    logger.info("  Downloaded valid     : %d", asset_summary.get("downloaded", 0))
    logger.info("  PutObject accepted   : %d", asset_summary.get("uploaded", 0))
    logger.info("  Post-upload verified : %d", asset_summary.get("post_upload_verified", 0))
    logger.info("  Existing scan/skipped: %d", asset_summary.get("already_stored", 0))
    logger.info("  Invalid magic        : %d", asset_summary.get("invalid_magic", 0))
    logger.info("  Terminal total       : %d", asset_summary.get("terminal_failed", 0))
    logger.info("  Retryable failed     : %d", asset_summary.get("retryable_failed", 0))
    logger.info("  Pending before       : %d", asset_summary.get("pending_before", 0))
    logger.info("  Pending after        : %d", asset_summary.get("remaining_pending", 0))
    logger.info("  Duration seconds     : %.3f", asset_summary.get("duration_seconds", 0.0))
    logger.info("=" * 60)

    return {
        "targets_due": targets_due,
        "targets_executable": targets_executable,
        "targets_deferred_cooldown": targets_deferred_cooldown,
        "bootstrap_planned": bootstrap_planned,
        "bootstrap_continue_planned": bootstrap_continue_planned,
        "incremental_planned": incremental_planned,
        "qualification_allowed": qualification_allowed,
        "robots_denied": robots_denied,
        "robots_unavailable": robots_unavailable,
        "crawl_success": crawl_success,
        "access_challenge": access_challenge,
        "technical_failure": technical_failure,
        "records_created": records_created,
        "observations_written": observations_written,
        "details_created": details_created,
        "mysql_posts_created": mysql_posts_created,
        "mysql_posts_existing": mysql_posts_existing,
        "mysql_observations_inserted": mysql_obs_inserted,
        "mysql_technical_duplicates": mysql_tech_duplicates,
        "target_states_persisted": target_states_persisted,
        "success_checkpoints_advanced": success_checkpoints_advanced,
        "health_states_updated": health_states_updated,
        "checkpoints_updated": sum(1 for c in checkpoints if c.get("checkpoint_updated") or c.get("target_state_persisted")),
        "duckdb_refresh": analytics_summary.get("status", "UNKNOWN") if analytics_summary else "UNKNOWN",
        "assets_attempted": asset_summary.get("attempted", 0),
        "assets_uploaded": asset_summary.get("uploaded", 0),
        "assets_post_upload_verified": asset_summary.get("post_upload_verified", 0),
        "assets_already_stored": asset_summary.get("already_stored", 0),
        "assets_retryable_failed": asset_summary.get("retryable_failed", 0),
        "assets_terminal_failed": asset_summary.get("terminal_failed", 0),
        "assets_invalid_magic": asset_summary.get("invalid_magic", 0),
        "assets_pending_before": asset_summary.get("pending_before", 0),
        "assets_remaining_pending": asset_summary.get("remaining_pending", 0),
        "assets_duration_seconds": asset_summary.get("duration_seconds", 0.0),
    }
