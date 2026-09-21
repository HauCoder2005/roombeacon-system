"""Conservative address specificity hints, not address validation."""

import re

_STREET = re.compile(
    r"(?:\b(?:đường|duong|phố|pho|hẻm|hem|ngõ|ngo|ngách)\s+\S|"
    r"^\s*(?:số\s+)?\d+[a-zA-Z]?(?:[/\-]\d+[a-zA-Z]?)*\s+[^\W\d_])",
    re.IGNORECASE,
)


def has_street_evidence(value: str | None) -> bool:
    """Recognize explicit street labels or a house number followed by a name."""
    return bool(value and _STREET.search(value))


def most_specific_address(*candidates: str | None) -> str | None:
    """Prefer street evidence, preserving source order for equally strong values."""
    values = [value for value in candidates if value and value.strip()]
    return next((value for value in values if has_street_evidence(value)), values[0] if values else None)
