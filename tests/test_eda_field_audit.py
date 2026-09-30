"""Coverage and funnel denominators must not confuse populated flags with success."""
import pandas as pd
from notebooks.utils.eda_field_audit import field_inventory, pipeline_edges, location_failure_labels


def test_inventory_keeps_derived_lists_blanks_and_false_status():
    frame = pd.DataFrame({'source_code': ['a', None, 'b'],
                          'street_text_extracted': [' ', None, 'Đường A'],
                          'ward_mapping_candidates': [[], ['A', 'B'], []],
                          'has_trusted_coordinate': [False, False, True]})
    result = field_inventory(frame, ['source_code'], []).set_index('field')
    assert set(result.index) == set(frame.columns)
    assert result.loc['street_text_extracted', 'present_count'] == 1
    assert result.loc['ward_mapping_candidates', 'unique_count'] == 2
    assert result.loc['has_trusted_coordinate', 'coverage_pct'] == 100
    assert result.loc['has_trusted_coordinate', 'origin'] == 'STATUS'
    assert 'success' in result.loc['has_trusted_coordinate', 'notes']


def test_funnel_counts_intersection_and_exposes_output_outside_parent():
    states = pd.DataFrame({'address': [True, True, False], 'street': [False, True, True],
                           'ward': [False, False, False]})
    result = pipeline_edges(states, [('address', 'street'), ('ward', 'street')])
    assert result.iloc[0].loss_count == 1
    assert result.iloc[0].conversion_pct == 50
    assert result.iloc[0].outside_parent_count == 1
    assert pd.isna(result.iloc[1].conversion_pct)


def test_failure_labels_do_not_claim_missing_marker_proves_absent_street():
    frame = pd.DataFrame({
        'best_address_text_normalized': [None, 'Phường 5, Quận 3', '123 Nguyễn Trãi', 'Sunrise City'],
        'street_text_extracted': [None] * 4,
        'ward_text_extracted': [None, 'Phường 5', None, None],
        'district_text_extracted': [None, 'Quận 3', None, None],
        'province_text_extracted': [None] * 4,
        'parse_status': ['NO_ADDRESS_EVIDENCE', 'PARTIALLY_PARSED', 'UNRECOGNIZED_FORMAT', 'UNRECOGNIZED_FORMAT']})
    labels = location_failure_labels(frame, 'street_text_extracted')
    assert labels.reason.tolist() == ['NO_USABLE_NORMALIZED_ADDRESS', 'ADMIN_ONLY_ADDRESS', 'PARSER_GAP_CANDIDATE', 'UNRECOGNIZED_FORMAT']
    assert labels.confidence.tolist() == ['CONFIRMED', 'INFERRED', 'INFERRED', 'NOT_VERIFIED']


def test_normalized_empty_does_not_claim_raw_evidence_absent():
    frame = pd.DataFrame({'best_address_text': ['📍'], 'best_address_text_normalized': [None],
                          'street_text_extracted': [None], 'parse_status': ['NO_ADDRESS_EVIDENCE']})
    result = location_failure_labels(frame, 'street_text_extracted')
    assert result.reason.iloc[0] == 'NO_USABLE_NORMALIZED_ADDRESS'


def test_city_prefix_is_not_a_street_cue():
    frame = pd.DataFrame({'best_address_text_normalized': ['Thành phố Hồ Chí Minh'],
                          'street_text_extracted': [None], 'parse_status': ['UNRECOGNIZED_FORMAT']})
    result = location_failure_labels(frame, 'street_text_extracted')
    assert result.reason.iloc[0] == 'ADMIN_ONLY_ADDRESS'
    assert result.confidence.iloc[0] == 'INFERRED'
