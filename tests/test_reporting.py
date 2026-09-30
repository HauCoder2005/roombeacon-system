from __future__ import annotations

from roombeacon_crawler.application.orchestration.reporting import summarize_run


def test_summarize_run_accepts_qualification_dict() -> None:
    summary = summarize_run(qualifications={"qualification_status": "READY"})

    assert summary["qualification_allowed"] == 1


def test_summarize_run_accepts_qualification_string() -> None:
    summary = summarize_run(qualifications="COOLDOWN_ACTIVE")

    assert summary["targets_deferred_cooldown"] == 1


def test_summarize_run_accepts_mixed_qualifications() -> None:
    summary = summarize_run(
        qualifications=[
            {"qualification_status": "READY"},
            "COOLDOWN_ACTIVE",
            '{"qualification_status": "DENIED_BY_ROBOTS"}',
        ]
    )

    assert summary["qualification_allowed"] == 1
    assert summary["targets_deferred_cooldown"] == 1
    assert summary["robots_denied"] == 1


def test_summarize_run_accepts_actual_single_target_xcom_shape() -> None:
    summary = summarize_run(
        plans=[{"mode": "INCREMENTAL"}],
        qualifications={"qualification_status": "READY"},
        crawl_results={
            "crawl_status": "success",
            "records_created": 5,
            "observations_written": 5,
            "details_success": 0,
        },
        persistence_results={
            "posts_created": 5,
            "posts_existing": 0,
            "observations_inserted": 5,
            "technical_duplicates": 0,
        },
        checkpoints={
            "target_state_persisted": True,
            "success_checkpoint_advanced": True,
            "health_state_updated": True,
        },
    )

    assert summary["crawl_success"] == 1
    assert summary["records_created"] == 5
    assert summary["mysql_posts_created"] == 5
    assert summary["target_states_persisted"] == 1


def test_summarize_run_accepts_json_strings_and_mixed_collections() -> None:
    summary = summarize_run(
        plans='[{"mode": "INCREMENTAL"}]',
        qualifications=[{"qualification_status": "READY"}, '"COOLDOWN_ACTIVE"'],
        crawl_results=['{"crawl_status": "success", "records_created": 2}', "timeout"],
        persistence_results='{"posts_created": 2, "observations_inserted": 2}',
        checkpoints=[
            '{"target_state_persisted": true}',
            {"health_state_updated": True},
        ],
    )

    assert summary["targets_due"] == 1
    assert summary["targets_deferred_cooldown"] == 1
    assert summary["crawl_success"] == 1
    assert summary["technical_failure"] == 1
    assert summary["records_created"] == 2
    assert summary["mysql_posts_created"] == 2
    assert summary["target_states_persisted"] == 1
    assert summary["health_states_updated"] == 1


def test_summarize_run_accepts_empty_and_null_collections() -> None:
    summary = summarize_run(
        plans=[],
        qualifications=None,
        crawl_results="",
        persistence_results=[],
        checkpoints=None,
    )

    assert summary["targets_due"] == 0
    assert summary["qualification_allowed"] == 0
    assert summary["crawl_success"] == 0
    assert summary["records_created"] == 0
    assert summary["mysql_posts_created"] == 0
    assert summary["target_states_persisted"] == 0
