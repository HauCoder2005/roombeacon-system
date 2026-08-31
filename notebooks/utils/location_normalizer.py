import re
import unicodedata

import pandas as pd

from enums.ward_mapping import EXACT_WARD_MAPPING


def normalize_text(value):
    if pd.isna(value):
        return None

    value = unicodedata.normalize(
        "NFC",
        str(value).strip().lower()
    )

    if not value:
        return None

    value = re.sub(
        r"\btp\.?\s*hcm\b|\btphcm\b",
        "thành phố hồ chí minh",
        value
    )

    value = re.sub(
        r"\bq\.?\s*(\d+)\b",
        r"quận \1",
        value
    )

    value = re.sub(
        r"\bp\.?\s*(\d+)\b",
        r"phường \1",
        value
    )

    value = re.sub(r"\s+", " ", value)

    return value


def extract_old_ward(text):
    if pd.isna(text) or not isinstance(text, str) or not text.strip():
        return None

    patterns = [
        r"\bphường\s+([^,]+)",
        r"\bxã\s+([^,]+)",
        r"\bthị trấn\s+([^,]+)"
    ]

    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)

        if match:
            value = match.group(1).strip()

            value = re.split(
                r"\b(quận|huyện|thành phố|tp)\b",
                value,
                maxsplit=1,
                flags=re.IGNORECASE
            )[0]

            return value.strip(" ,-").title()

    return None


def extract_old_district(text):
    if pd.isna(text) or not isinstance(text, str) or not text.strip():
        return None

    patterns = [
        r"\b(quận\s+\d+)\b",
        r"\b(quận\s+[^,]+)",
        r"\b(huyện\s+[^,]+)",
        r"\b(thành phố\s+thủ đức)\b",
        r"\b(thành phố\s+vũng tàu)\b",
        r"\b(thành phố\s+bà rịa)\b",
        r"\b(thành phố\s+thuận an)\b",
        r"\b(thành phố\s+dĩ an)\b",
        r"\b(thành phố\s+thủ dầu một)\b",
        r"\b(thành phố\s+bến cát)\b",
        r"\b(thành phố\s+tân uyên)\b"
    ]

    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)

        if match:
            return match.group(1).strip().title()

    return None


def normalize_location(df):
    result = df.copy()

    required_columns = {"address", "location"}

    missing_columns = required_columns - set(result.columns)

    if missing_columns:
        raise KeyError(
            f"Missing required columns: {sorted(missing_columns)}"
        )

    result["location_source"] = (
        result["address"]
        .fillna(result["location"])
        .apply(normalize_text)
    )

    result["old_ward"] = (
        result["location_source"]
        .apply(extract_old_ward)
    )

    result["old_district"] = (
        result["location_source"]
        .apply(extract_old_district)
    )

    result["current_ward"] = result.apply(
        lambda row: EXACT_WARD_MAPPING.get(
            (
                row["old_ward"],
                row["old_district"]
            )
        ),
        axis=1
    )

    result["mapping_status"] = (
        result["current_ward"]
        .notna()
        .map({
            True: "exact",
            False: "unmapped"
        })
    )

    return result