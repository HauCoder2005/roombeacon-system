"""Regression contract for Task 08 source-preserving text standardization."""

import unicodedata

import pandas as pd
import pytest

from notebooks.utils import text_standardization


def standardize_text(value):
    """Call the wished-for production API so RED is a test failure, not collection error."""
    return text_standardization.standardize_text(value)


def trace_text_standardization(value):
    """Call the wished-for trace API through the real production module."""
    return text_standardization.trace_text_standardization(value)


apply_text_standardization = text_standardization.apply_text_standardization


@pytest.mark.parametrize(
    ('raw', 'expected'),
    [
        ('📍 Phường 7, Quận 3', 'Phường 7, Quận 3'),
        ('🏠 Phòng trọ đẹp ⭐ gần trường', 'Phòng trọ đẹp gần trường'),
        ('💰 3 triệu/tháng', '3 triệu/tháng'),
        ('25/16/1, , Tăng Nhơn Phú TP. Hồ Chí Minh',
         '25/16/1, Tăng Nhơn Phú TP. Hồ Chí Minh'),
        ('60-62, Trần Văn Kỷ, , Bình Thạnh', '60-62, Trần Văn Kỷ, Bình Thạnh'),
        ('  Phường   Tân   Phú  ', 'Phường Tân Phú'),
        ('25 m²', '25 m²'),
        ('850.000 đồng/tháng', '850.000 đồng/tháng'),
        ('3.5 triệu/tháng', '3.5 triệu/tháng'),
        ('Phường Tăng Nhơn Phú', 'Phường Tăng Nhơn Phú'),
        ('Phường\u200b Tăng Nhơn Phú', 'Phường Tăng Nhơn Phú'),
        ('Cần nhượng lại phòng gấp ,,', 'Cần nhượng lại phòng gấp'),
        ('342, Đường Hoàng Hoa Thám, , ,', '342, Đường Hoàng Hoa Thám'),
        (None, None),
        ('', None),
        ('   \t\r\n ', None),
    ],
)
def test_standardize_text_matches_task_08_contract(raw, expected):
    """Removing any required stage must make at least one literal example fail."""
    assert standardize_text(raw) == expected


def test_emoji_sequences_leave_no_joiner_selector_modifier_or_keycap_artifacts():
    """Deleting only a base pictograph must not leave invisible sequence fragments."""
    raw = 'Phòng 👨\u200d👩\u200d👧\u200d👦 đẹp ✈️ số 1️⃣'
    result = standardize_text(raw)
    assert result == 'Phòng đẹp số 1'
    assert all(
        char not in result
        for char in ('\u200d', '\ufe0e', '\ufe0f', '\u20e3')
    )


def test_meaningful_real_estate_syntax_and_vietnamese_are_preserved():
    """A broad non-alphanumeric or symbol-category deletion would fail this contract."""
    raw = '25/16/1; 60-62, 3.5: #12 100% + ₫ $ 25 m², Phường Tăng Nhơn Phú'
    assert standardize_text(raw) == raw
    assert unicodedata.is_normalized('NFC', standardize_text(raw))


def test_decimal_comma_is_not_rewritten_as_a_separator():
    """Comma spacing must not corrupt a numeric decimal or thousands representation."""
    assert standardize_text('3,5 triệu/tháng') == '3,5 triệu/tháng'
    assert standardize_text('850,000 đồng/tháng') == '850,000 đồng/tháng'
    assert standardize_text(',5 triệu/tháng') == ',5 triệu/tháng'


def test_invisible_controls_are_removed_without_merging_words():
    """Control cleanup must preserve word boundaries for whitespace controls."""
    raw = 'Phường\ufeff\u2060 Tân\x00\tPhú'
    assert standardize_text(raw) == 'Phường Tân Phú'
    assert standardize_text('Phường\u200bTân Phú') == 'Phường Tân Phú'
    assert standardize_text('12\u200bA Nguyễn Trãi') == '12 A Nguyễn Trãi'


def test_invisible_cleanup_cannot_defer_unicode_composition_to_a_second_pass():
    """Removing a format character must compose newly adjacent combining marks immediately."""
    raw = 'e\u200b\u0302\u0301'
    assert standardize_text(raw) == 'ế'
    assert standardize_text(standardize_text(raw)) == 'ế'


def test_unicode_is_composed_to_nfc():
    """Removing NFC normalization must make decomposed Vietnamese unequal to expected."""
    decomposed = unicodedata.normalize('NFD', 'Phường Tăng Nhơn Phú')
    result = standardize_text(decomposed)
    assert result == 'Phường Tăng Nhơn Phú'
    assert unicodedata.is_normalized('NFC', result)


def test_complete_pipeline_is_idempotent():
    """A stage that creates new cleanup work on a second pass violates the contract."""
    corpus = [
        '📍  Phường 7  ,  , Quận 3',
        '🏠 Phòng\u200b đẹp ⭐',
        '3,5 triệu/tháng',
        '25 m²',
        None,
        '   ',
    ]
    for raw in corpus:
        once = standardize_text(raw)
        assert standardize_text(once) == once


def test_trace_reports_each_stage_independently():
    """Notebook audit counts must come from actual sequential stage changes."""
    trace = trace_text_standardization('e\u0302́\u200b 📍  Phường 7  , , Quận 3')
    assert trace['after'] == 'ế Phường 7, Quận 3'
    assert trace['reasons'] == (
        'UNICODE_NORMALIZED',
        'INVISIBLE_CHAR_REMOVED',
        'ICON_REMOVED',
        'WHITESPACE_NORMALIZED',
        'PUNCTUATION_CLEANED',
    )


def test_apply_standardization_preserves_raw_source_columns():
    """Writing normalized output must never alter the source DataFrame columns."""
    source = pd.DataFrame({
        'title_raw': ['🏠 Phòng đẹp', None],
        'full_address_text': ['25/16/1, , Tăng Nhơn Phú', '  '],
        'location_raw': ['📍 Phường 7, Quận 3', None],
        'best_address_text': ['📍 Phường 7, Quận 3', None],
    })
    original = source.copy(deep=True)
    result = source
    for field in source.columns:
        result = apply_text_standardization(result, field, f'{field}_normalized')

    pd.testing.assert_frame_equal(source, original)
    pd.testing.assert_frame_equal(result[list(source.columns)], original)
    assert result.loc[0, 'title_raw_normalized'] == 'Phòng đẹp'
    assert result.loc[1, 'full_address_text_normalized'] is None
