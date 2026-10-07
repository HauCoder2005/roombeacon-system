"""Snapshot, missingness and Task 11 gates shared by the two official notebooks."""

from datetime import datetime, timezone
from pathlib import Path
import re

import numpy as np
import pandas as pd

from .price_area_validation import (
    canonicalize_decimal, classify_area_raw_semantic, classify_price_raw_semantic,
    parse_area, parse_price, validate_area, validate_price,
)

CORE_FIELDS = ['title_raw', 'price_amount', 'area_value', 'best_address_text']
ADDRESS_FIELDS = ['full_address_text', 'location_raw', 'best_address_text']
EVIDENCE_FIELDS = [
    'evidence_observation_id', 'evidence_version_time_matches',
    'evidence_price_id', 'price_raw', 'currency', 'period',
    'evidence_area_id', 'area_raw', 'price_lineage_aligned', 'area_lineage_aligned',
]


def load_snapshot(conn, project_root):
    """Read one snapshot using conn and project_root; return listings, evidence, context.

    The canonical source remains read-only. One SQL statement restricts raw
    evidence to the contributing observation; no full history enters Pandas.
    Separate upstream table scans are not a global MySQL snapshot guarantee:
    alignment flags block recovery if values diverge during ingestion.
    """
    started = datetime.now(timezone.utc).isoformat()
    sql = (Path(project_root) / 'notebooks/sql/eda_snapshot.sql').read_text()
    combined = conn.execute(sql).df()
    combined_rows = len(combined)
    evidence_rows = (
        int(combined['evidence_observation_id'].notna().sum())
        if 'evidence_observation_id' in combined else 0
    )
    aligned_rows = (
        int((combined['price_lineage_aligned'] | combined['area_lineage_aligned']).sum())
        if {'price_lineage_aligned', 'area_lineage_aligned'} <= set(combined) else 0
    )
    required = {'rental_post_id', 'source_code', 'source_listing_id', *CORE_FIELDS,
                *ADDRESS_FIELDS, *EVIDENCE_FIELDS}
    assert required <= set(combined), f'Missing required columns: {required - set(combined)}'
    assert combined.rental_post_id.notna().all(), 'Null listing identity'
    assert len(combined) == combined.rental_post_id.nunique(), 'Snapshot identity multiplication'
    # The final SELECT is LEFT-anchored on latest, so an empty combined result
    # proves that v_latest_posts itself is empty rather than an evidence-join loss.
    assert len(combined) > 0, (
        'Empty source snapshot; analysis cannot proceed '
        f'(latest_rows=0, evidence_rows={evidence_rows}, '
        f'combined_rows={combined_rows}, aligned_rows={aligned_rows})'
    )
    latest = combined.drop(columns=EVIDENCE_FIELDS).copy()
    evidence = combined[['rental_post_id', *EVIDENCE_FIELDS]].copy()
    context = {
        'snapshot_started_utc': started,
        'snapshot_completed_utc': datetime.now(timezone.utc).isoformat(),
        'row_count': len(latest), 'field_count': len(latest.columns),
        'source_count': latest.source_code.nunique(), 'view_name': 'v_latest_posts',
        'grain': 'one row per rental_post_id',
        'raw_grain': 'latest child ID of contributing version; post ID + time + version ID tie-break',
        'max_latest_observed_at': str(latest.latest_observed_at.max()),
    }
    return latest, evidence, context


def missing_mask(frame):
    """For frame, return Boolean null/empty/whitespace masks; zero stays present."""
    mask = frame.isna()
    for field in frame.select_dtypes(include=['object', 'string']).columns:
        mask[field] |= frame[field].astype('string').str.fullmatch(r'\s*', na=False)
    return mask.astype(bool)


def semantic_states(series, numeric=False):
    """Classify a series with optional numeric rules; return exclusive state labels."""
    result = pd.Series('PRESENT', index=series.index, dtype='string')
    if numeric:
        values = pd.to_numeric(series, errors='coerce')
        result.loc[values.eq(0)] = 'ZERO'
        result.loc[values.lt(0)] = 'NEGATIVE'
        result.loc[series.notna() & (~np.isfinite(values))] = 'INVALID_NONFINITE_OR_TEXT'
    else:
        text = series.astype('string')
        result.loc[text.eq('').fillna(False)] = 'EMPTY'
        result.loc[text.str.fullmatch(r'\s+', na=False)] = 'WHITESPACE'
        result.loc[text.str.lower().eq('nan').fillna(False)] = 'LITERAL_NAN'
    result.loc[series.isna()] = 'NULL'
    return result


def raw_semantics(latest, evidence, kind):
    """Classify missing numeric evidence for price/area; return reconciled labels."""
    field = 'price_amount' if kind == 'price' else 'area_value'
    classifier = classify_price_raw_semantic if kind == 'price' else classify_area_raw_semantic
    labels = pd.Series([
        classifier(raw, value) for raw, value in zip(evidence[f'{kind}_raw'], latest[field])
    ], index=latest.index, dtype='string')
    labels = labels.replace({
        'RAW_PRESENT_NUMERIC_PARSE_FAILED': 'NUMERIC_PARSE_GAP_CANDIDATE',
        'PHYSICAL_NULL': 'NO_RAW', 'EMPTY_STRING': 'EMPTY_RAW',
        'WHITESPACE_ONLY': 'WHITESPACE_RAW',
    })
    labels.loc[latest[field].notna()] = 'EXISTING_VALUE'
    values = pd.to_numeric(latest[field], errors='coerce')
    labels.loc[latest[field].notna() & (values.le(0) | ~np.isfinite(values))] = 'INVALID_EXISTING'
    labels.loc[~evidence[f'{kind}_lineage_aligned'].fillna(False)] = 'UNKNOWN_LINEAGE'
    return labels


def _safe_recovery_text(raw, kind):
    """For raw and numeric kind, return whether its full syntax supports safe recovery.

    The existing parser extracts the first numeric token. Restrict automatic
    acceptance to explicit units (or a single area number), never ranges,
    dimensions or a daily/per-square-metre price. Decimal compound prices need
    review because the legacy parser strips separators in compound terms.
    """
    if not isinstance(raw, str):
        return False
    text = raw.lower().strip()
    number = r'\d+(?:[.,]\d+)*'
    if kind == 'area':
        return bool(re.fullmatch(fr'{number}\s*(?:m2|m²|m\^2|m\s+2|mét vuông)?', text))
    simple = fr'{number}\s*(?:triệu|tr|tỷ|nghìn|ngàn|k|vnđ|vnd|đồng)'
    compound = r'(?:\d+\s*tỷ\s+\d+\s*(?:triệu|tr)|\d+\s*(?:triệu|tr)\s+\d+\s*(?:nghìn|ngàn|k))'
    return bool(re.fullmatch(fr'(?:{simple}|{compound})(?:\s*/\s*tháng)?', text))


def validate_numeric_candidates(latest, evidence, kind):
    """Gate Task 11 candidates for latest/evidence and kind; return an audit frame.

    Existing valid values take precedence. Only aligned, unambiguous, accepted
    recovery fills a physical null. Suspicious/invalid values stay visible in
    the original columns; no rows are filtered and mismatches are not overwritten.
    """
    field = 'price_amount' if kind == 'price' else 'area_value'
    parser = parse_price if kind == 'price' else parse_area
    validator = validate_price if kind == 'price' else validate_area
    raw = evidence[f'{kind}_raw']
    existing = latest[field].map(lambda v: canonicalize_decimal(v, 2))
    reparsed = raw.map(parser).map(lambda v: canonicalize_decimal(v, 2))
    existing_gate = existing.map(validator)
    reparse_gate = reparsed.map(validator)
    aligned = evidence[f'{kind}_lineage_aligned'].fillna(False)
    safe_text = raw.map(lambda value: _safe_recovery_text(value, kind))
    units = pd.Series(True, index=latest.index)
    if kind == 'price':
        units = (evidence.currency.fillna('').str.upper().eq('VND') &
                 evidence.period.fillna('').str.upper().eq('MONTH'))
    keep = existing_gate.eq('ACCEPTED_CLEAN') & aligned & units
    recover = (latest[field].isna() & aligned & units & safe_text &
               reparse_gate.eq('ACCEPTED_CLEAN'))
    candidate = existing.where(keep, None).copy()
    candidate.loc[recover] = reparsed.loc[recover]
    action = pd.Series('KEEP_NULL_OR_FLAG', index=latest.index, dtype='string')
    action.loc[keep] = 'VALIDATED_EXISTING'
    action.loc[recover] = 'REPARSE_ACCEPTED_CLEAN'
    action.loc[~aligned] = 'UNKNOWN_LINEAGE'
    regression = pd.Series('NO_EXISTING', index=latest.index, dtype='string')
    present = latest[field].notna()
    regression.loc[present & reparsed.isna()] = 'REPARSE_NULL'
    regression.loc[present & reparsed.notna() & existing.eq(reparsed)] = 'CANONICAL_MATCH'
    regression.loc[present & reparsed.notna() & ~existing.eq(reparsed)] = 'DIFFERENT_REVIEW'
    regression.loc[~aligned] = 'UNKNOWN_LINEAGE'
    result = pd.DataFrame({
        'rental_post_id': latest.rental_post_id, 'source_code': latest.source_code,
        'raw': raw, 'existing': existing, 'reparsed': reparsed,
        'semantic': raw_semantics(latest, evidence, kind),
        'existing_gate': existing_gate, 'reparse_gate': reparse_gate,
        'lineage_aligned': aligned, 'safe_recovery_syntax': safe_text,
        'unit_contract': units, 'regression': regression,
        'action': action, 'clean_candidate': candidate,
    })
    assert len(result) == len(latest)
    assert result.loc[recover, 'clean_candidate'].notna().all()
    assert not (recover & ~aligned).any()
    assert result.loc[keep, 'clean_candidate'].equals(existing.loc[keep])
    return result
