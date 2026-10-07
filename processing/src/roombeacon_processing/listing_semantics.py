"""Conservative deterministic semantics for RoomBeacon rental listings.

Rules use text evidence only. Numeric price is intentionally absent from this
API so price magnitude can never determine business intent or rental scope.
"""
from __future__ import annotations

import re
import unicodedata
import pandas as pd

BUSINESS_TARGET_DEFINITION = (
    "Predict the asking rental price for an ordinary individual rental "
    "listing/unit represented by RoomBeacon."
)

INTENT_VALUES = frozenset({"RENT", "SALE", "TRANSFER", "UNKNOWN"})
SCOPE_VALUES = frozenset({"SINGLE_OR_ORDINARY_UNIT", "WHOLE_BUILDING", "MULTI_UNIT_BUSINESS", "UNKNOWN"})

def normalize_semantic_text(value: object) -> str:
    """Normalize casing/spacing while preserving Vietnamese lexical accents.

    Intent-bearing words such as ``bán`` must remain distinguishable from
    ordinary words such as ``ban công``.  Accent-insensitive matching is only
    used by rules whose surrounding lexical context is independently strong.
    """
    if value is None or pd.isna(value):
        return ""
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", str(value).casefold())).strip()


def _accent_fold(value: str) -> str:
    text = unicodedata.normalize("NFKD", value)
    return "".join(char for char in text if not unicodedata.combining(char)).replace("đ", "d")

SALE_RULES_NATIVE = [
    ("TITLE_EXPLICIT_URGENT_SALE", re.compile(r"\b(?:cần\s+)?bán\s+gấp\b|\bcần\s+bán\b")),
    ("TITLE_EXPLICIT_PROPERTY_SALE", re.compile(r"\bbán\s+(?:nhà|đất|căn hộ|building|tòa nhà|dãy trọ|khu trọ|phòng trọ|mặt bằng|biệt thự|kho xưởng|shophouse|chdv)\b")),
    ("TITLE_EXPLICIT_SALE", re.compile(r"^(?:phòng trọ:\s*)?bán\s+(?:nhà|đất|căn hộ|building|tòa nhà|mặt bằng|giá tốt|gấp)\b")),
    ("TITLE_PROPERTY_SALE_PRICE_CONTEXT", re.compile(r"(?=.*\b(?:nhà|căn|căn hộ|mặt tiền|góc 2 mt|đất|building|tòa nhà|hxh|hẻm|tiện xây mới)\b)(?=.*(?:\b\d+[\.,]?\d*\s*tỷ\b|\b\d+[\.,]?\d*\s*tr\s*/\s*m2\b))(?!.*\b(?:cho thuê|/\s*tháng|mỗi tháng)\b).+")),
]
SALE_RULES_FOLDED = [
    ("TITLE_EXPLICIT_URGENT_SALE", re.compile(r"\b(?:can\s+ban\s+gap|ban\s+gap\s+(?:nha|dat|can\s+ho|toa\s+nha|phong\s+tro|mat\s+bang))\b")),
    ("TITLE_EXPLICIT_PROPERTY_SALE", re.compile(r"\b(?:can\s+)?ban\s+(?:nha|dat|can\s+ho|building|toa\s+nha|day\s+tro|khu\s+tro|phong\s+tro|mat\s+bang|biet\s+thu|kho\s+xuong|shophouse|chdv)\b")),
    ("TITLE_EXPLICIT_SALE", re.compile(r"^(?:phong\s+tro:\s*)?ban\s+(?:nha|dat|can\s+ho|building|toa\s+nha|mat\s+bang|gia\s+tot|gap)\b")),
]
TRANSFER_RULES_NATIVE = [
    ("TITLE_CONTRACT_SALE_TRANSFER", re.compile(r"\bbán\s+hợp\s+đồng(?:\s+nhà)?\b")),
    ("TITLE_EXPLICIT_CONTRACT_TRANSFER", re.compile(r"\b(?:sang|chuyển|nhượng)\s+nhượng\b|\b(?:sang|chuyển)\s+hợp\s+đồng\b|\bnhượng\s+lại\b|\bchuyển\s+nhượng\s+căn\s+hộ\b|\bcho\s+(?:cố|thục|thụt)\b|\bcầm\s+cố\b")),
    ("TITLE_EXPLICIT_TRANSFER", re.compile(r"\bcần\s+sang(?:\s+lại)?\b|\bsang\s+lại(?:\s+phòng)?\b")),
    ("TITLE_EXPLICIT_ROOM_TRANSFER", re.compile(r"\b(?:nhượng|sang|pass)\s+(?:lại\s+)?(?:phòng|căn\s+hộ|studio|chdv|ktx)\b")),
    ("TITLE_MULTI_UNIT_TRANSFER", re.compile(r"\bsang\s+(?:\d{1,3}\s*(?:căn\s+hộ|phòng|p)\b|dãy\s+(?:nhà\s+)?trọ\b|chdv\b)")),
]
TRANSFER_RULES_FOLDED = [
    ("TITLE_CONTRACT_SALE_TRANSFER", re.compile(r"\bban\s+hop\s+dong(?:\s+nha)?\b")),
    ("TITLE_EXPLICIT_CONTRACT_TRANSFER", re.compile(r"\b(?:sang|chuyen|nhuong)\s+nhuong\b|\b(?:sang|chuyen)\s+hop\s+dong\b|\bnhuong\s+lai\b|\bchuyen\s+nhuong\s+can\s+ho\b|\bcho\s+(?:co|thuc|thut)\b|\bcam\s+co\b")),
    ("TITLE_EXPLICIT_TRANSFER", re.compile(r"\bcan\s+sang(?:\s+lai)?\b|\bsang\s+lai(?:\s+phong)?\b")),
    ("TITLE_EXPLICIT_ROOM_TRANSFER", re.compile(r"\b(?:nhuong|sang|pass)\s+(?:lai\s+)?(?:phong|can\s+ho|studio|chdv|ktx)\b")),
    ("TITLE_MULTI_UNIT_TRANSFER", re.compile(r"\bsang\s+(?:\d{1,3}\s*(?:can\s+ho|phong|p)\b|day\s+(?:nha\s+)?tro\b|chdv\b)")),
]
RENT_RULES_NATIVE = [
    ("TITLE_EXPLICIT_RENT_OFFER", re.compile(r"\bcho\s+thuê\b|\bphòng\s+(?:trọ\s+)?cho\s+thuê\b|\b(?:căn\s+hộ|nhà)\s+cho\s+thuê\b|\btìm\s+người\s+thuê\b")),
    ("TITLE_RENTAL_UNIT", re.compile(r"\bphòng\s+trọ\b|\bcăn\s+hộ\b|\bstudio\b|\bnhà\s+nguyên\s+căn\b")),
]
RENT_RULES_FOLDED = [
    ("TITLE_EXPLICIT_RENT_OFFER", re.compile(r"\bcho\s+thue\b|\bphong\s+(?:tro\s+)?cho\s+thue\b|\b(?:can\s+ho|nha)\s+cho\s+thue\b|\btim\s+nguoi\s+thue\b")),
    ("TITLE_RENTAL_UNIT", re.compile(r"\bphong\s+tro\b|\bcan\s+ho\b|\bstudio\b|\bnha\s+nguyen\s+can\b")),
]
WHOLE_BUILDING_RULES = [
    ("TITLE_WHOLE_BUILDING", re.compile(r"\b(?:cho\s+thu[eê]\s+)?nguy[eê]n\s+t[oò]a(?:\s+nh[aà])?\b|\bcho\s+thu[eê]\s+(?:c[aả]|to[aà]n\s+b[oộ])\s+t[oò]a\s+nh[aà]\b|\bnguy[eê]n\s+t[oò]a\b|\bc[aả]\s+t[oò]a\b|\bto[aà]n\s+b[oộ]\s+t[oò]a\b")),
]
MULTI_UNIT_RULES_NATIVE = [
    ("TITLE_MULTI_ROOM_RENTAL", re.compile(r"\b(?:cho\s+thuê|sang|nhượng)\s+(?:[4-9]|[1-9]\d{1,2})\s*(?:phòng|p)\b")),
    ("TITLE_HOTEL_ROOM_AGGREGATE", re.compile(r"\b(?:khách\s+sạn|căn\s+hộ\s+dịch\s+vụ|chdv)\b[^\n]{0,45}\b(?:[4-9]|[1-9]\d{1,2})\s*(?:phòng|p|căn)\b")),
    ("TITLE_MULTI_UNIT_BUSINESS", re.compile(r"\b(?:cả|nguyên|sang)\s+dãy\s+(?:nhà\s+)?trọ\b|\bkinh\s+doanh\s+phòng\s+trọ\b")),
    ("TITLE_MULTI_ROOM_AGGREGATE", re.compile(r"\b(?:tòa\s+nhà|dãy(?: nhà)? trọ|chdv)\b[^\n]{0,45}\b\d{1,3}\s*(?:p|phòng|căn\s+hộ)\b|\b\d{1,3}\s*(?:p|phòng|căn\s+hộ)\b[^\n]{0,45}\b(?:tòa\s+nhà|dãy(?: nhà)? trọ|chdv)\b")),
    ("TITLE_MULTI_UNIT_TRANSFER_COUNT", re.compile(r"\bsang\s+\d{1,3}\s*(?:căn\s+hộ|phòng|p)\b")),
]
MULTI_UNIT_RULES_FOLDED = [
    ("TITLE_MULTI_ROOM_RENTAL", re.compile(r"\b(?:cho\s+thue|sang|nhuong)\s+(?:[4-9]|[1-9]\d{1,2})\s*(?:phong|p)\b")),
    ("TITLE_HOTEL_ROOM_AGGREGATE", re.compile(r"\b(?:khach\s+san|can\s+ho\s+dich\s+vu|chdv)\b[^\n]{0,45}\b(?:[4-9]|[1-9]\d{1,2})\s*(?:phong|p|can)\b")),
    ("TITLE_MULTI_UNIT_BUSINESS", re.compile(r"\b(?:ca|nguyen|sang)\s+day\s+(?:nha\s+)?tro\b|\bkinh\s+doanh\s+phong\s+tro\b")),
    ("TITLE_MULTI_ROOM_AGGREGATE", re.compile(r"\b(?:toa\s+nha|day(?: nha)? tro|chdv)\b[^\n]{0,45}\b\d{1,3}\s*(?:p|phong|can\s+ho)\b|\b\d{1,3}\s*(?:p|phong|can\s+ho)\b[^\n]{0,45}\b(?:toa\s+nha|day(?: nha)? tro|chdv)\b")),
    ("TITLE_MULTI_UNIT_TRANSFER_COUNT", re.compile(r"\bsang\s+\d{1,3}\s*(?:can\s+ho|phong|p)\b")),
]

def _match(text: str, rules: list[tuple[str, re.Pattern]]) -> tuple[str | None, str | None]:
    for reason, pattern in rules:
        match = pattern.search(text)
        if match:
            return reason, match.group(0)
    return None, None

def classify_listing_semantics(title: object) -> dict[str, str]:
    """Classify title with explicit precedence: SALE > TRANSFER > RENT > UNKNOWN.
    
    Uses native accented representation for primary rules and contextual-only
    accent-folded fallback. Conflicting explicit SALE vs RENT yields UNKNOWN.
    """
    text_native = normalize_semantic_text(title)
    text_folded = _accent_fold(text_native)
    sale_reason, sale_evidence = _match(text_native, SALE_RULES_NATIVE)
    if not sale_reason:
        cand_reason, cand_evidence = _match(text_folded, SALE_RULES_FOLDED)
        if cand_reason:
            if text_native == text_folded or not re.search(r"\bb[ạảà]n\b", text_native):
                sale_reason, sale_evidence = cand_reason, cand_evidence
    transfer_reason, transfer_evidence = _match(text_native, TRANSFER_RULES_NATIVE)
    if not transfer_reason:
        transfer_reason, transfer_evidence = _match(text_folded, TRANSFER_RULES_FOLDED)

    body_native = re.sub(r"^(?:(?:cho\s+thuê\s+)?(?:phòng\s+trọ|nhà\s+trọ|căn\s+hộ)):\s*", "", text_native).strip()
    rent_reason, rent_evidence = _match(text_native, [RENT_RULES_NATIVE[0]])
    if not rent_reason:
        unit_reason, unit_ev = _match(body_native or text_native, [RENT_RULES_NATIVE[1]])
        if unit_reason:
            rent_reason, rent_evidence = unit_reason, unit_ev
    if not rent_reason:
        rent_reason, rent_evidence = _match(text_folded, RENT_RULES_FOLDED)

    if sale_reason and rent_reason == "TITLE_EXPLICIT_RENT_OFFER" and not sale_evidence.startswith("phòng trọ:"):
        intent = "UNKNOWN"
        intent_reason = "CONFLICTING_SALE_RENT_EVIDENCE"
        intent_evidence = f"{sale_evidence} vs {rent_evidence}"
    elif sale_reason:
        intent, intent_reason, intent_evidence = "SALE", sale_reason, sale_evidence
    elif transfer_reason:
        intent, intent_reason, intent_evidence = "TRANSFER", transfer_reason, transfer_evidence
    elif rent_reason:
        intent, intent_reason, intent_evidence = "RENT", rent_reason, rent_evidence
    else:
        intent, intent_reason, intent_evidence = "UNKNOWN", "INSUFFICIENT_TITLE_EVIDENCE", ""

    multi_reason, multi_evidence = _match(text_native, MULTI_UNIT_RULES_NATIVE)
    if not multi_reason:
        multi_reason, multi_evidence = _match(text_folded, MULTI_UNIT_RULES_FOLDED)
    whole_reason, whole_evidence = _match(text_native, WHOLE_BUILDING_RULES)
    if not whole_reason:
        whole_reason, whole_evidence = _match(text_folded, WHOLE_BUILDING_RULES)
    if whole_reason:
        scope, scope_reason, scope_evidence = "WHOLE_BUILDING", whole_reason, whole_evidence
    elif multi_reason:
        scope, scope_reason, scope_evidence = "MULTI_UNIT_BUSINESS", multi_reason, multi_evidence
    elif text_native and intent in {"RENT", "TRANSFER"} and not multi_reason and not whole_reason:
        scope, scope_reason, scope_evidence = "SINGLE_OR_ORDINARY_UNIT", "TITLE_ORDINARY_UNIT_NO_AGGREGATE_EVIDENCE", rent_evidence or transfer_evidence or ""
    else:
        scope, scope_reason, scope_evidence = "UNKNOWN", "INSUFFICIENT_SCOPE_EVIDENCE", ""
    return {
        "listing_intent": intent, "listing_intent_reason": intent_reason,
        "listing_intent_evidence": intent_evidence or "",
        "rental_scope": scope, "rental_scope_reason": scope_reason,
        "rental_scope_evidence": scope_evidence or "",
    }

def apply_listing_semantics(frame: pd.DataFrame, title_column: str = "title_clean") -> pd.DataFrame:
    result = frame.copy(deep=False)
    semantic = pd.DataFrame(
        [classify_listing_semantics(value) for value in result[title_column]],
        index=result.index,
    )
    for column in semantic:
        result[column] = semantic[column]
    return result

def semantic_model_eligibility(frame: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    """Return model compatibility independently of numeric target validity.

    UNKNOWN is retained unless conflicting SALE/TRANSFER/aggregate evidence exists.
    """
    incompatible_intent = frame["listing_intent"].isin(["SALE", "TRANSFER"])
    incompatible_scope = frame["rental_scope"].isin(["WHOLE_BUILDING", "MULTI_UNIT_BUSINESS"])
    eligible = ~(incompatible_intent | incompatible_scope)
    reason = pd.Series("SEMANTICALLY_COMPATIBLE", index=frame.index, dtype="string")
    reason.loc[incompatible_scope] = "EXCLUDE_" + frame.loc[incompatible_scope, "rental_scope"].astype("string")
    reason.loc[incompatible_intent] = "EXCLUDE_" + frame.loc[incompatible_intent, "listing_intent"].astype("string")
    reason.loc[incompatible_intent & incompatible_scope] = (
        "EXCLUDE_" + frame.loc[incompatible_intent & incompatible_scope, "listing_intent"].astype("string")
        + "_AND_" + frame.loc[incompatible_intent & incompatible_scope, "rental_scope"].astype("string")
    )
    return eligible, reason
