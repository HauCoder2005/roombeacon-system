"""Meaningful boundaries for the official read-only notebook pipeline."""
from pathlib import Path
from decimal import Decimal

import duckdb
import pandas as pd

from notebooks.utils.notebook_audit import (
    load_snapshot, missing_mask, raw_semantics, semantic_states,
    validate_numeric_candidates,
)


def test_missing_representations_are_disjoint_and_zero_is_present():
    values = pd.Series([None, '', '  ', 'nan', 'text'])
    assert semantic_states(values).tolist() == ['NULL', 'EMPTY', 'WHITESPACE', 'LITERAL_NAN', 'PRESENT']
    numeric = pd.DataFrame({'value': [None, 0, -1, 2]})
    assert missing_mask(numeric).value.tolist() == [True, False, False, False]
    assert semantic_states(numeric.value, numeric=True).tolist() == ['NULL', 'ZERO', 'NEGATIVE', 'PRESENT']


def frames(raw, existing, kind='price'):
    """Return aligned latest/evidence frames for raw/existing candidate cases."""
    field = 'price_amount' if kind == 'price' else 'area_value'
    latest = pd.DataFrame({'rental_post_id': range(len(raw)), 'source_code': 'test', field: existing})
    evidence = pd.DataFrame({f'{kind}_raw': raw, f'{kind}_lineage_aligned': True,
                             'currency': 'VND', 'period': 'MONTH'})
    return latest, evidence


def test_price_recovery_keeps_negotiable_suspicious_ranges_and_daily_prices_unaccepted():
    raw = ['Thỏa thuận', 'Thương lượng', '4 đồng/tháng', '3 triệu 500 nghìn',
           '2-3 triệu', '3 triệu/ngày', '1.5 tỷ 300 triệu', None]
    latest, evidence = frames(raw, [None] * len(raw))
    result = validate_numeric_candidates(latest, evidence, 'price')
    assert result.action.eq('REPARSE_ACCEPTED_CLEAN').tolist() == [False, False, False, True, False, False, False, False]
    assert result.loc[3, 'clean_candidate'] == Decimal('3500000.00')
    assert result.loc[2, 'reparse_gate'] == 'SUSPICIOUS'
    assert result.loc[0, 'semantic'] == 'NEGOTIABLE_NON_NUMERIC'


def test_existing_precedence_and_lineage_and_unit_gates():
    latest, evidence = frames(['4 triệu 400 nghìn', '5 triệu', '6 triệu', '7 triệu'],
                              [4000000, None, None, 7000000])
    evidence.loc[1, 'price_lineage_aligned'] = False
    evidence.loc[2, 'currency'] = 'USD'
    evidence.loc[3, 'period'] = 'DAY'
    result = validate_numeric_candidates(latest, evidence, 'price')
    assert result.loc[0, 'clean_candidate'] == Decimal('4000000.00')
    assert result.loc[0, 'regression'] == 'DIFFERENT_REVIEW'
    assert result.loc[1:, 'clean_candidate'].isna().all()
    assert result.loc[1, 'action'] == 'UNKNOWN_LINEAGE'


def test_area_decimal_canonicalization_and_ambiguous_dimensions():
    latest, evidence = frames(['18.999', '20 m²', '4 x 5 m2', '0 m2', None],
                              [19, None, None, None, None], 'area')
    result = validate_numeric_candidates(latest, evidence, 'area')
    assert result.loc[0, 'regression'] == 'CANONICAL_MATCH'
    assert result.loc[1, 'clean_candidate'] == Decimal('20.00')
    assert result.loc[2:, 'clean_candidate'].isna().all()
    assert result.semantic.value_counts().sum() == len(latest)


def test_unknown_lineage_cannot_be_classified_as_confirmed_parse_gap():
    latest, evidence = frames(['5 triệu', 'Thỏa thuận'], [None, None])
    evidence.loc[0, 'price_lineage_aligned'] = False
    assert raw_semantics(latest, evidence, 'price').tolist() == ['UNKNOWN_LINEAGE', 'NEGOTIABLE_NON_NUMERIC']


def test_snapshot_joins_identity_and_timestamp_with_canonical_tie_break():
    # Isolated synthetic SQL fixture: never uses the real source or connection factory.
    conn = duckdb.connect(':memory:')
    conn.execute('CREATE SCHEMA mysql_db')
    conn.execute('''CREATE TABLE mysql_db.rental_post_versions AS SELECT * FROM
        (VALUES (10, 1, TIMESTAMP '2026-01-01'), (11, 1, TIMESTAMP '2026-01-01'),
                (20, 2, TIMESTAMP '2026-01-01')) t(id, rental_post_id, observed_at)''')
    conn.execute('''CREATE TABLE mysql_db.post_prices AS SELECT * FROM
        (VALUES (1, 1, 10, 'OLD', 1., 'VND', 'MONTH'),
                (2, 1, 11, 'OLDER_CHILD', 2., 'VND', 'MONTH'),
                (3, 1, 11, 'ALIGNED', 3., 'VND', 'MONTH'),
                (4, 2, 20, 'OTHER_POST', 4., 'VND', 'MONTH'))
        t(id, rental_post_id, rental_post_version_id, price_raw, price_amount, currency, period)''')
    conn.execute('''CREATE TABLE mysql_db.post_details AS SELECT * FROM
        (VALUES (1, 1, 11, '20 m2', 20.), (2, 2, 20, '30 m2', 30.))
        t(id, rental_post_id, rental_post_version_id, area_raw, area_value)''')
    conn.execute('''CREATE VIEW v_latest_posts AS SELECT rental_post_id,
        'test' AS source_code, rental_post_id AS source_listing_id, 'title' AS title_raw,
        price_amount, CASE WHEN rental_post_id=1 THEN 20. ELSE 30. END AS area_value,
        NULL AS full_address_text, NULL AS location_raw, NULL AS best_address_text,
        TIMESTAMP '2026-01-01' AS latest_observed_at
        FROM mysql_db.post_prices WHERE id IN (3,4)''')
    latest, evidence, context = load_snapshot(conn, Path(__file__).resolve().parents[1])
    assert context['row_count'] == 2
    assert evidence.price_raw.tolist() == ['ALIGNED', 'OTHER_POST']
    assert evidence.evidence_observation_id.tolist() == [11, 20]
    assert evidence.evidence_version_time_matches.tolist() == [2, 1]
    assert evidence.price_lineage_aligned.all()
    # A divergence between the canonical value and evidence must block recovery.
    conn.register('frozen_latest', latest)
    conn.execute('CREATE OR REPLACE VIEW v_latest_posts AS SELECT * REPLACE (99. AS price_amount) FROM frozen_latest')
    _, evidence2, _ = load_snapshot(conn, Path(__file__).resolve().parents[1])
    assert not evidence2.price_lineage_aligned.any()
    conn.close()
