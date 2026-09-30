"""Read-only analytical summaries; processing rules stay in their existing helpers."""
import json
import re

import numpy as np
import pandas as pd

from .notebook_audit import missing_mask


def field_inventory(frame, base_fields, evidence_fields):
    """Inventory every runtime column, including list evidence and populated flags.

    Nullable is observed in this snapshot, not a database schema constraint.
    Unknown fields remain visible and require semantic review.
    """
    missing = missing_mask(frame)
    rows = []
    for field in frame:
        status = (pd.api.types.is_bool_dtype(frame[field]) or
                  any(t in field for t in ('status', 'reason', 'action', 'gate', 'semantic', 'regression')) or
                  field in ('best_address_source', 'spatial_search_mode'))
        if field == 'source_code':
            domain = 'SOURCE'
        elif field in ('rental_post_id', 'source_listing_id', 'url') or field.startswith('evidence_'):
            domain = 'IDENTITY'
        elif field.startswith('price_') or field in ('currency', 'period'):
            domain = 'PRICE'
        elif field.startswith('area_'):
            domain = 'AREA'
        elif field.startswith(('ward_', 'district_', 'province_', 'street_')):
            domain = 'ADMIN LOCATION'
        elif field.startswith(('map_', 'coordinate_', 'has_trusted_')):
            domain = 'COORDINATE'
        elif field.endswith('_at') or field == 'active_days':
            domain = 'TEMPORAL'
        elif 'address' in field or field in ('location_raw', 'parse_status', 'spatial_search_mode'):
            domain = 'ADDRESS'
        elif 'title' in field:
            domain = 'TEXT'
        else:
            domain = 'UNCLASSIFIED'
        if field in base_fields:
            stage = 'BASE SNAPSHOT'
        elif field in evidence_fields:
            stage = 'ALIGNED RAW EVIDENCE'
        elif field.endswith('_normalized') and not field.startswith('ward_'):
            stage = 'TASK 08'
        elif field.startswith('ward_') and field != 'ward_text_extracted':
            stage = 'TASK 10'
        elif field.endswith('_text_extracted') or field == 'parse_status':
            stage = 'TASK 09'
        elif domain in ('PRICE', 'AREA'):
            stage = 'TASK 11 AUDIT'
        elif domain in ('COORDINATE', 'ADDRESS'):
            stage = 'LOCATION QUALITY AUDIT'
        else:
            stage = 'UNCLASSIFIED'
        values = frame.loc[~missing[field], field].map(
            lambda v: json.dumps(v, ensure_ascii=False, sort_keys=True) if isinstance(v, (list, dict)) else str(v))
        unique = values.nunique()
        rows.append(dict(
            field=field, category='STATUS' if status else domain, domain=domain,
            origin='STATUS' if status else ('RAW' if field in evidence_fields or field.endswith('_raw') else
                    'BASE' if field in base_fields else 'DERIVED'),
            processing_stage=stage, dtype=str(frame[field].dtype),
            nullable_observed=bool(missing[field].any()), present_count=int((~missing[field]).sum()),
            missing_count=int(missing[field].sum()), coverage_pct=(~missing[field]).mean() * 100,
            missing_pct=missing[field].mean() * 100, unique_count=unique,
            cardinality='EMPTY' if unique == 0 else 'CONSTANT' if unique == 1 else
                        'UNIQUE' if unique == len(values) else 'REPEATED',
            examples=' | '.join(values.drop_duplicates().head(3).str.slice(0, 110)),
            source_dependency='source_code; source × field table (including missing source)',
            source_breakdown_available=True, semantic_audit='03: exclusive representation states',
            quality_audit=f'05: {domain.lower()}',
            root_cause_audit='06: evidence/status diagnostics' if domain in
                ('PRICE', 'AREA', 'ADDRESS', 'ADMIN LOCATION', 'COORDINATE') else
                '02/05: observed checks only; cause not established',
            notes=('Population is not success; inspect status distribution.' if status else
                   'Empty candidate lists are present evidence, not resolved wards.' if field.endswith('candidates') else
                   'Nullable describes observed missingness, not DDL.')))
    return pd.DataFrame(rows)


def pipeline_edges(states, edges):
    """Measure actual parent/child intersections; independent branches stay separate."""
    rows = []
    for parent, child in edges:
        p, c = states[parent].fillna(False).astype(bool), states[child].fillna(False).astype(bool)
        denominator = int(p.sum())
        retained = int((p & c).sum())
        rows.append(dict(parent=parent, stage=child, count=int(c.sum()),
                         coverage_pct=c.mean() * 100, parent_count=denominator,
                         retained_count=retained, loss_count=int((p & ~c).sum()),
                         loss_pct=(denominator - retained) / denominator * 100 if denominator else np.nan,
                         conversion_pct=retained / denominator * 100 if denominator else np.nan,
                         outside_parent_count=int((~p & c).sum())))
    return pd.DataFrame(rows)


def location_failure_labels(frame, field):
    """Conservative clues for absent components; never produce replacement values.

    Markers are audit cues, not another address parser. No marker does not prove
    absent evidence. ADMIN_ONLY is inferred only for explicitly prefixed segments.
    """
    text = frame.best_address_text_normalized.astype('string').fillna('')
    absent = missing_mask(frame[[field]])[field]
    reason = pd.Series('NOT_VERIFIED', index=frame.index)
    confidence = pd.Series('NOT_VERIFIED', index=frame.index)
    markers = {
        'street_text_extracted': r'(?i)\b(?:đường|hẻm)\b|(?<!thành )\bphố\b|^\s*\d+[\d/.-]*\s+[^\W\d_]',
        'ward_text_extracted': r'(?i)\b(?:phường|xã|thị trấn)\b|\bP\s*\.\s*\d',
        'district_text_extracted': r'(?i)\b(?:quận|huyện|thủ đức)\b|\bQ\s*\.\s*\d',
        'province_text_extracted': r'(?i)\b(?:tỉnh|thành phố|hồ chí minh|hà nội|hcm|tphcm)\b',
    }
    unrecognized = frame.parse_status.eq('UNRECOGNIZED_FORMAT')
    reason.loc[unrecognized] = 'UNRECOGNIZED_FORMAT'
    if field == 'street_text_extracted':
        admin_only = text.map(lambda value: bool(value.strip()) and all(
            re.match(r'(?i)^(?:phường\b|xã\b|quận\b|huyện\b|thành phố\b|tỉnh\b|P\s*\.|Q\s*\.|TP\s*\.|HCM\b|TPHCM\b)', part.strip())
            for part in re.split(r'[,;]', value) if part.strip()))
        reason.loc[admin_only] = 'ADMIN_ONLY_ADDRESS'
        confidence.loc[admin_only] = 'INFERRED'
    cue = text.str.contains(markers[field], regex=True, na=False)
    reason.loc[cue] = 'PARSER_GAP_CANDIDATE'
    confidence.loc[cue] = 'INFERRED'
    no_evidence = text.str.strip().eq('')
    reason.loc[no_evidence] = 'NO_USABLE_NORMALIZED_ADDRESS'
    confidence.loc[no_evidence] = 'CONFIRMED'
    reason.loc[~absent] = 'OUTPUT_PRESENT'
    confidence.loc[~absent] = 'CONFIRMED'
    return pd.DataFrame({'reason': reason, 'confidence': confidence})
