import re
import unicodedata

import pandas as pd


_DECORATIVE_RANGES = (
    (0x1F000, 0x1FAFF),  # Mahjong through Symbols and Pictographs Extended-A.
    (0x1FC00, 0x1FFFD),  # Reserved supplementary pictograph range.
    (0x2600, 0x27BF),    # Miscellaneous Symbols and Dingbats.
    (0x2B00, 0x2BFF),    # Supplemental arrows and decorative shapes.
)
_DECORATIVE_SINGLETONS = frozenset({
    *range(0x231A, 0x231C),
    *range(0x23E9, 0x23F4),
    *range(0x23F8, 0x23FB),
    0x20E3,  # Combining enclosing keycap; retain its meaningful base digit.
})
_VARIATION_SELECTOR_RANGES = ((0xFE00, 0xFE0F), (0xE0100, 0xE01EF))
_ZERO_WIDTH_SEPARATORS = frozenset({0x200B, 0x2060, 0xFEFF})


def _in_ranges(codepoint: int, ranges: tuple[tuple[int, int], ...]) -> bool:
    """Return whether a Unicode codepoint belongs to one of the closed ranges."""
    return any(start <= codepoint <= end for start, end in ranges)


def _same_value(left: object, right: object) -> bool:
    """Compare scalar stage values while treating physical nulls as equal."""
    if pd.isna(left) and pd.isna(right):
        return True
    return left == right


def normalize_unicode(text: object) -> object:
    """Normalize Unicode to NFC form if it's a valid string."""
    if pd.isna(text) or not isinstance(text, str):
        return text
    return unicodedata.normalize('NFC', text)


def remove_invisible_characters(text: object) -> object:
    """Remove formatting noise and replace invisible separators with normal spaces."""
    if pd.isna(text) or not isinstance(text, str):
        return text

    cleaned = []
    for index, char in enumerate(text):
        codepoint = ord(char)
        category = unicodedata.category(char)
        if _in_ranges(codepoint, _VARIATION_SELECTOR_RANGES):
            continue
        if category in {'Zl', 'Zp', 'Zs'}:
            cleaned.append(' ')
        elif category == 'Cc':
            # Whitespace controls separate words; other controls carry no text meaning.
            if char.isspace():
                cleaned.append(' ')
        elif category == 'Cf':
            following = text[index + 1] if index + 1 < len(text) else ''
            if following and unicodedata.combining(following):
                # Removing the artifact reconnects a base letter to its mark.
                continue
            if codepoint in _ZERO_WIDTH_SEPARATORS:
                cleaned.append(' ')
            # ZWJ/ZWNJ, bidi controls and emoji tags carry no text token.
        else:
            cleaned.append(char)
    return unicodedata.normalize('NFC', ''.join(cleaned))


def remove_decorative_icons(text: object) -> object:
    """Remove pictographic decoration without deleting general Unicode symbols."""
    if pd.isna(text) or not isinstance(text, str):
        return text
    cleaned = ''.join(
        char for char in text
        if ord(char) not in _DECORATIVE_SINGLETONS
        and not _in_ranges(ord(char), _DECORATIVE_RANGES)
    )
    return unicodedata.normalize('NFC', cleaned)


def normalize_whitespace(text: object) -> object:
    """Trim text and collapse all remaining whitespace runs to one normal space."""
    if pd.isna(text) or not isinstance(text, str):
        return text
    return re.sub(r'\s+', ' ', text).strip()


def normalize_safe_punctuation(text: object) -> object:
    """Clean empty comma segments and spacing while preserving numeric commas."""
    if pd.isna(text) or not isinstance(text, str):
        return text

    # Treat only repeated comma segments as malformed. Valid single-comma
    # spacing, including decimal commas and address separators, is left intact.
    compact = re.sub(r'(?:\s*,){2,}\s*$', '', text)
    compact = re.sub(r'^(?:\s*,){2,}\s*', '', compact)
    compact = re.sub(r'\s*,(?:\s*,)+\s*', ', ', compact)
    compact = re.sub(r'\s+,', ',', compact)
    return compact.strip()


def trace_text_standardization(text: object) -> dict[str, object]:
    """Return final text and the ordered transformations that changed its representation."""
    current = text
    reasons = []
    stages = (
        ('UNICODE_NORMALIZED', normalize_unicode),
        ('INVISIBLE_CHAR_REMOVED', remove_invisible_characters),
        ('ICON_REMOVED', remove_decorative_icons),
        ('WHITESPACE_NORMALIZED', normalize_whitespace),
        ('PUNCTUATION_CLEANED', normalize_safe_punctuation),
    )
    for reason, transform in stages:
        transformed = transform(current)
        if not _same_value(current, transformed):
            reasons.append(reason)
        current = transformed

    if isinstance(current, str) and not current:
        current = None
        reasons.append('EMPTY_TO_NULL')
    return {'before': text, 'after': current, 'reasons': tuple(reasons)}


def standardize_text(text: object) -> object:
    """Return one canonical, source-preserving Task 08 text representation."""
    return trace_text_standardization(text)['after']


def apply_text_standardization(
    df: pd.DataFrame, 
    source_col: str, 
    target_col: str,
    do_unicode: bool = True,
    do_whitespace: bool = True,
) -> pd.DataFrame:
    """Write a derived standardized column without mutating source columns."""
    result = df.copy(deep=False)
    if do_unicode and do_whitespace:
        series = result[source_col].map(standardize_text)
    else:
        series = result[source_col].copy()
        if do_unicode:
            series = series.map(normalize_unicode)
        series = series.map(remove_invisible_characters).map(remove_decorative_icons)
        if do_whitespace:
            series = series.map(normalize_whitespace)
        series = series.map(normalize_safe_punctuation)
        series = series.map(lambda value: None if isinstance(value, str) and not value else value)
    # pandas' inferred string dtype represents Python None as float NaN. Keep an
    # object-backed derived column so the Task 08 empty-to-null contract remains
    # explicit and stable at the helper boundary.
    series = series.astype(object).where(series.notna(), None)
    result[target_col] = series
    return result


def apply_text_standardization_batch(
    df: pd.DataFrame,
    columns: dict[str, str],
) -> pd.DataFrame:
    """Standardize several columns while evaluating each distinct value once."""
    result = df.copy(deep=False)
    combined = pd.concat(
        [result[source_col] for source_col in columns], ignore_index=True
    )
    unique_values = pd.unique(combined.dropna())
    standardized = {value: standardize_text(value) for value in unique_values}
    for source_col, target_col in columns.items():
        series = result[source_col].map(standardized)
        result[target_col] = series.astype(object).where(series.notna(), None)
    return result
