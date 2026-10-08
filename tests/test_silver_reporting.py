import pandas as pd

from notebooks.utils.silver_reporting import (
    duplicate_group_summary,
    flag_reason_breakdown,
    multi_flag_distribution,
    status_summary,
    text_change_summary,
)


def test_status_summary_reports_exact_rows_and_percentage():
    result = status_summary(pd.Series(["READY", "READY", "REVIEW"]), "Row Status")

    assert result.to_dict("records") == [
        {"Row Status": "READY", "Rows": 2, "Percentage (%)": 66.67},
        {"Row Status": "REVIEW", "Rows": 1, "Percentage (%)": 33.33},
    ]


def test_text_change_summary_distinguishes_changes_from_cleaned_to_null():
    bronze = pd.DataFrame({"title_raw": [" A ", "same", "  ", None]})
    silver = pd.DataFrame({"title_clean": ["A", "same", None, None]})

    result = text_change_summary(bronze, silver, {"Title": ("title_raw", "title_clean")})

    row = result.iloc[0]
    assert row["Raw Available"] == 3
    assert row["Clean Available"] == 2
    assert row["Changed Rows"] == 2
    assert row["Unchanged Rows"] == 2
    assert row["Cleaned to NULL"] == 1
    assert row["Changed (%)"] == 50.0


def test_flag_reason_breakdown_uses_only_existing_silver_statuses():
    silver = pd.DataFrame({
        "row_quality_status": ["READY", "READY_WITH_FLAGS", "READY_WITH_FLAGS"],
        "price_outlier_flag": [False, True, False],
        "area_outlier_flag": [False, False, True],
        "coordinate_trust_reason": ["TRUSTED_UNIQUE_POINT", "MISSING_COORDINATE_PAIR", "UNTRUSTED_PROVIDER"],
        "duplicate_candidate_status": ["UNIQUE_FINGERPRINT", "POSSIBLE_DUPLICATE", "UNIQUE_FINGERPRINT"],
        "temporal_quality_status": ["VALID", "VALID", "REQUIRES_REVIEW"],
        "price_quality_status": ["VALIDATED_EXISTING", "VALIDATED_EXISTING", "MISSING_OR_REVIEW"],
        "area_quality_status": ["VALIDATED_EXISTING"] * 3,
        "price_parser_comparison_status": ["MATCH", "DISAGREEMENT", "MATCH"],
        "price_area_quality_status": ["CHECKED_NO_FLAG", "PRICE_OUTLIER_REVIEW", "INSUFFICIENT_DATA"],
        "ward_mapping_status": ["MAPPED", "UNMAPPED", "AMBIGUOUS"],
        "duplicate_scope": ["NOT_APPLICABLE", "CROSS_SOURCE", "NOT_APPLICABLE"],
    })

    result, flags = flag_reason_breakdown(silver)

    counts = dict(zip(result["Flag Reason"], result["Affected Rows"]))
    assert counts["Price Outlier"] == 1
    assert counts["Area Outlier"] == 1
    assert counts["Coordinate Missing"] == 1
    assert counts["Coordinate Untrusted"] == 1
    assert counts["Possible Duplicate"] == 1
    assert counts["Price Parser Disagreement"] == 1
    assert counts["Price × Area Review"] == 1
    assert counts["Cross-source Duplicate Candidate"] == 1
    assert counts["Temporal Review"] == 1
    assert flags.shape == (3, len(result))


def test_multi_flag_distribution_buckets_four_or_more_without_scoring():
    flags = pd.DataFrame({
        "a": [False, True, True],
        "b": [False, True, True],
        "c": [False, False, True],
        "d": [False, False, True],
        "e": [False, False, True],
    })

    result = multi_flag_distribution(flags)

    assert result.set_index("Flag Count")["Rows"].to_dict() == {
        "0": 1, "1": 0, "2": 1, "3": 0, "4+": 1,
    }


def test_duplicate_group_summary_labels_categorical_scope():
    # build_silver_dataset() returns duplicate_scope as a pandas Categorical.
    silver = pd.DataFrame(
        {
            "rental_post_id": [1, 2, 3, 4],
            "source_code": ["mogi", "nhatot", "mogi", "mogi"],
            "duplicate_candidate_status": ["POSSIBLE_DUPLICATE"] * 4,
            "duplicate_candidate_group": ["g1", "g1", "g2", "g2"],
            "duplicate_scope": pd.Categorical(["CROSS_SOURCE", "CROSS_SOURCE", "SAME_SOURCE", "SAME_SOURCE"]),
        }
    )

    groups, distribution = duplicate_group_summary(silver)

    assert groups[["Group ID", "Candidate Scope"]].to_dict("records") == [
        {"Group ID": "g1", "Candidate Scope": "Cross-source"},
        {"Group ID": "g2", "Candidate Scope": "Same-source"},
    ]
    assert distribution.to_dict("records") == [{"Group Size": 2, "Candidate Groups": 2}]
