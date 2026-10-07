import re
import unicodedata
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Optional, Dict, Any, Tuple
import pandas as pd

@dataclass(frozen=True)
class PriceEvidenceCandidate:
    source_field: str
    raw_text: str
    matched_text: str
    parsed_value: Decimal
    rule: str
    confidence: str = "HIGH"
    role: str = "AMBIGUOUS"
    cadence: str = "MONTHLY_COMPATIBLE"


@dataclass(frozen=True)
class AreaEvidence:
    value: Optional[Decimal]
    status: str
    matched_text: str = ""


PRICE_ROLE_NON_RENT = [
    ("DISCOUNT", re.compile(r"\b(?:gi[ảã]m?(?:\s+giá)?|ưu\s+đãi)\b")),
    ("PROMOTION", re.compile(r"\b(?:tặng|khuyến\s+mãi|voucher|lì\s*xì|h[oỗổ]\s*trợ|free)\b")),
    ("DEPOSIT", re.compile(r"\b(?:tiền\s+)?(?:đặt\s+)?cọc\b")),
    ("UTILITY_FEE", re.compile(r"\b(?:điện|nước|wifi|internet|phí\s+(?:dịch\s+vụ|quản\s+lý))\b")),
    ("PARKING_FEE", re.compile(r"\b(?:phí\s+(?:xe|giữ\s+xe)|giữ\s+xe)\b")),
    ("TRANSFER_AMOUNT", re.compile(r"\b(?:sang|nhượng|chuyển\s+nhượng|pass)\b")),
    ("SALE_PRICE", re.compile(r"\b(?:bán|mua)\b")),
]
NON_MONTHLY_CADENCE = re.compile(
    r"/(?:\s*)?(?:ngày(?:\s*đêm)?|đêm|giờ|tuần|năm|m2|m²)\b|"
    r"\b(?:mỗi|theo)\s+(?:ngày|đêm|giờ|tuần|năm)\b|"
    r"/(?:\s*)?(?:kwh|người)\b|\b\d+\s*(?:ngày|đêm|năm)\b|\bqua\s+đêm\b"
)
RENT_ROLE_CONTEXT = re.compile(
    r"\b(?:giá|thuê|cho\s+thuê|tiền\s+phòng|giá\s+phòng|chỉ|từ)\b"
)


def _classify_price_context(text: str, start: int, end: int) -> tuple[str, str]:
    """Classify one money expression by nearby lexical role and cadence."""
    nearby = text[max(0, start - 45):min(len(text), end + 35)]
    prefix = text[max(0, start - 35):start]
    suffix = text[end:min(len(text), end + 25)]
    cadence = "NON_MONTHLY" if NON_MONTHLY_CADENCE.search(nearby) else "MONTHLY_COMPATIBLE"
    if re.search(r"[-–]\s*$", prefix):
        return "DISCOUNT", cadence
    for role, pattern in PRICE_ROLE_NON_RENT:
        if pattern.search(prefix) or pattern.search(suffix):
            return role, cadence
    role = "RENT_PRICE" if RENT_ROLE_CONTEXT.search(prefix) else "AMBIGUOUS"
    return role, cadence


def _parse_shorthand(m: re.Match) -> Decimal:
    major = Decimal(m.group(1))
    suffix = m.group(2)
    fraction = Decimal(suffix) / (Decimal(10) ** len(suffix))
    return ((major + fraction) * Decimal(1_000_000)).quantize(Decimal("1"))


def _parse_compound_tr_k(m: re.Match) -> Decimal:
    return (Decimal(m.group(1)) * 1_000_000 + Decimal(m.group(2)) * 1_000).quantize(Decimal("1"))


def _parse_k_suffix(m: re.Match) -> Decimal:
    num_str = re.sub(r"[\.,]", "", m.group(1))
    return (Decimal(num_str) * 1_000).quantize(Decimal("1"))


def _parse_vnd_full(m: re.Match) -> Decimal:
    num_str = re.sub(r"[\.,]", "", m.group(1))
    return Decimal(num_str).quantize(Decimal("1"))


PRICE_PATTERNS = [
    # 1. Full VND numbers with million suffix: 2.800.000 triệu, 3.500.000tr (at least 2 dots: >= 1,000,000)
    (re.compile(r"\b(\d{1,3}(?:[\.,]\d{3}){2,})\s*(?:triệu|tr)\b"),
     _parse_vnd_full,
     "PRICE_VND_MILLION_REDUNDANT"),
    # 2. Full VND numbers with currency unit: 2.800.000 vnđ, 3.000.000 đ, 500.000 đồng
    (re.compile(r"\b(\d{1,3}(?:[\.,]\d{3})+)\s*(?:vnđ|vnd|đồng|đ)\b"),
     _parse_vnd_full,
     "PRICE_VND_FULL"),
    # 3. Large plain VND numbers: 1000000tr -> 1,000,000
    (re.compile(r"\b(\d{6,8})\s*(?:vnđ|vnd|đồng|đ|tr|triệu)\b"),
     lambda m: Decimal(m.group(1)),
     "PRICE_VND_PLAIN"),
    # 4. 4-digit tr shorthand: 2990tr, 1200tr -> 2,990,000 / 1,200,000
    (re.compile(r"\b([1-9]\d{3,4})\s*tr\b"),
     lambda m: Decimal(m.group(1)) * 1000,
     "PRICE_TR_THOUSAND_SHORTHAND"),
    # 5. Compound: 3 triệu 800 nghìn, 3tr800k, 3tr 800 ngàn
    (re.compile(r"\b(\d{1,3})\s*(?:triệu|tr)\s*(\d{1,3})\s*(?:nghìn|ngàn|k)\b"),
     _parse_compound_tr_k,
     "PRICE_COMPOUND_MILLION_THOUSAND"),
    # 6. Million shorthand: 3tr7, 3tr75, 3tr750, 3 triệu 7, 3 triệu 700
    (re.compile(r"\b(\d{1,3})\s*(?:triệu|tr)\s*(\d{1,3})\b(?!\s*(?:nghìn|ngàn|k|m2|m²|mét|p|phòng|pn|wc|tầng|năm))"),
     _parse_shorthand,
     "PRICE_MILLION_SHORTHAND"),
    # 7. k notation: 3800k, 2400k, 2.400k, 3.800k
    (re.compile(r"\b(\d{1,3}(?:[\.,]\d{3})+|\d{3,5})\s*k\b"),
     _parse_k_suffix,
     "PRICE_K_SUFFIX"),
    # 8. Standard million: 3.5 triệu, 3,5tr, 3 triệu, 3tr, 1.500 triệu, 1,380tr (up to 3 decimals)
    (re.compile(r"\b(\d{1,3}(?:[\.,]\d{1,3})?)\s*(?:triệu|tr)\b(?!\s*(?:nghìn|ngàn|k|/(?:m2|m²|ngày|đêm|năm|\d+\s*năm)|trên\s*m2|mỗi\s*m2))"),
     lambda m: (Decimal(m.group(1).replace(",", ".")) * 1_000_000).quantize(Decimal("1")),
     "PRICE_MILLION_STANDARD"),
    # 9. Billion: 1 tỷ, 1.5 tỷ, 38 tỷ (True billion remains billion)
    (re.compile(r"\b(\d+(?:[\.,]\d+)?)\s*tỷ\b"),
     lambda m: (Decimal(m.group(1).replace(",", ".")) * 1_000_000_000).quantize(Decimal("1")),
     "PRICE_BILLION"),
]

RENTAL_RANGE_PATTERN = re.compile(
    r"\b(\d{1,2}[\.,]\d{3})\s*(?:-|–|đến)\s*"
    r"(\d{1,2}[\.,]\d{3})\s*(?:vnđ|vnd|đồng|đ)\b"
)


def extract_price_evidence_candidates(text_value: Optional[str], source_field: str = "title") -> list[PriceEvidenceCandidate]:
    if text_value is None or pd.isna(text_value):
        return []
    text = unicodedata.normalize("NFC", str(text_value).casefold())
    candidates: list[PriceEvidenceCandidate] = []
    occupied: list[tuple[int, int]] = []
    # A unit-less range ending in "đ" is common but does not identify one
    # asking price. Preserve it as auditable ambiguous evidence; never choose
    # an endpoint or silently average it.
    for match in RENTAL_RANGE_PATTERN.finditer(text):
        role, cadence = _classify_price_context(text, match.start(), match.end())
        candidates.append(PriceEvidenceCandidate(
            source_field=source_field,
            raw_text=str(text_value),
            matched_text=match.group(0),
            parsed_value=Decimal(re.sub(r"[\.,]", "", match.group(2))) * 1000,
            rule="PRICE_AMBIGUOUS_THOUSAND_RANGE",
            confidence="REVIEW",
            role="AMBIGUOUS",
            cadence=cadence,
        ))
        occupied.append(match.span())
    for pattern, convert, rule_name in PRICE_PATTERNS:
        for match in pattern.finditer(text):
            if any(match.start() < end and start < match.end() for start, end in occupied):
                continue
            try:
                val = convert(match)
                role, cadence = _classify_price_context(text, match.start(), match.end())
                candidates.append(PriceEvidenceCandidate(
                    source_field=source_field,
                    raw_text=str(text_value),
                    matched_text=match.group(0),
                    parsed_value=val,
                    rule=rule_name,
                    confidence="HIGH",
                    role=role,
                    cadence=cadence,
                ))
                occupied.append(match.span())
            except (InvalidOperation, ValueError):
                continue
    return candidates


def parse_rental_price_evidence(text_value: Optional[str]) -> tuple[Optional[Decimal], str]:
    """Parse one unambiguous Vietnamese monetary shorthand from listing text.

    The accepted forms carry their own monetary unit, so area/street numbers
    cannot become price evidence. Multiple distinct monetary values are left
    ambiguous rather than guessed.
    """
    candidates = extract_price_evidence_candidates(text_value, source_field="title")
    distinct = {cand.parsed_value for cand in candidates}
    if len(distinct) != 1:
        return None, ""
    value = next(iter(distinct))
    evidence = next(cand.matched_text for cand in candidates if cand.parsed_value == value)
    return value, evidence


def parse_rental_price_evidence_candidate(
    text_value: Optional[str], source_field: str = "title"
) -> Optional[PriceEvidenceCandidate]:
    candidates = extract_price_evidence_candidates(text_value, source_field=source_field)
    distinct = {cand.parsed_value for cand in candidates}
    if len(distinct) != 1:
        return None
    value = next(iter(distinct))
    return next(cand for cand in candidates if cand.parsed_value == value)


def evaluate_price_target_trust(
    clean_price: Optional[float | Decimal],
    price_quality_status: str,
    price_parser_comparison_status: str,
    price_lineage_aligned: bool,
    raw_price: Optional[str] = None,
    title: Optional[str] = None,
    listing_intent: Optional[str] = None,
    rental_scope: Optional[str] = None,
) -> tuple[str, str, str, Optional[float]]:
    """Evaluate numeric rental price target trust according to canonical contract.

    Returns:
        (status, reason, evidence, model_value)
    where status is in:
        TRUSTED_EXISTING, TRUSTED_REPARSED, SUSPECT_UNIT_SCALE,
        PARSER_DISAGREEMENT_REVIEW, INSUFFICIENT_EVIDENCE, MISSING
    """
    raw_str = str(raw_price) if raw_price is not None and not pd.isna(raw_price) else ""
    raw_lower = raw_str.lower()

    # K0. Cadence check: rental asking price must be total monthly unit rent
    title_str = str(title) if title is not None and not pd.isna(title) else ""
    title_lower = title_str.lower()
    if any(cad in raw_lower for cad in ["/m2", "/m²", "tr/m2", "đồng/m2", "đ/m2", "nghìn/m2", "/ngày", "/đêm", "/năm", "/2 năm", "/3 năm"]):
        return (
            "SUSPECT_UNIT_SCALE",
            "CADENCE_NOT_MONTHLY_UNIT",
            f"price_raw:{raw_str}",
            None,
        )
    if any(cad in title_lower for cad in ["/m2", "/m²", "tr/m2", "đồng/m2/tháng", "đ/m2", "/2 năm", "/3 năm", "/ngày", "theo ngày", "ngắn ngày", "qua đêm", "cho cố", "cho thục", "cho thụt"]):
        return (
            "SUSPECT_UNIT_SCALE",
            "CADENCE_NOT_MONTHLY_UNIT",
            f"title:{title_str}",
            None,
        )

    title_cand = parse_rental_price_evidence_candidate(title, source_field="title") if title else None
    if title_cand and title_cand.rule == "PRICE_AMBIGUOUS_THOUSAND_RANGE":
        return ("SUSPECT_UNIT_SCALE", "AMBIGUOUS_RENT_PRICE_RANGE", f"title:{title_cand.matched_text}", None)
    if title_cand and title_cand.cadence == "NON_MONTHLY":
        return ("INSUFFICIENT_EVIDENCE", "NON_MONTHLY_TEXT_PRICE", f"title:{title_cand.matched_text}", None)
    if title_cand and title_cand.role == "AMBIGUOUS" and listing_intent == "RENT":
        title_cand = PriceEvidenceCandidate(
            **{**title_cand.__dict__, "role": "RENT_PRICE"}
        )
    if title_cand and title_cand.role != "RENT_PRICE":
        title_cand = None
    if title_cand and (listing_intent in {"SALE", "TRANSFER"} or rental_scope in {"WHOLE_BUILDING", "MULTI_UNIT_BUSINESS"}):
        title_cand = None
    title_val = float(title_cand.parsed_value) if title_cand else None
    title_text = title_cand.matched_text if title_cand else ""

    clean_num = None
    if clean_price is not None and not pd.isna(clean_price):
        try:
            v = float(clean_price)
            if v > 0:
                clean_num = v
        except (ValueError, TypeError):
            pass

    # K1. MISSING
    if clean_num is None and title_val is None:
        return ("MISSING", "NO_USABLE_PRICE_EVIDENCE", "", None)

    # Check for contradictory / ambiguous prices in title (distinct > 1)
    if title is not None and not pd.isna(title):
        all_title_cands = extract_price_evidence_candidates(title, source_field="title")
        distinct_title_vals = {
            c.parsed_value for c in all_title_cands
            if c.role == "RENT_PRICE" and c.cadence == "MONTHLY_COMPATIBLE" and c.confidence == "HIGH"
        }
        if len(distinct_title_vals) > 1:
            return ("SUSPECT_UNIT_SCALE", "CONTRADICTORY_TEXT_PRICE_SCALE", f"title:{title}", None)

    # K2. STRONG EXPLICIT TEXTUAL EVIDENCE
    if title_val is not None:
        if clean_num is not None:
            ratio = clean_num / title_val if title_val > 0 else 0
            if ratio >= 10.0 or ratio <= 0.1 or abs(clean_num - title_val) > 1000:
                return (
                    "TRUSTED_REPARSED",
                    "EXPLICIT_TEXT_PRICE_OVERRIDE_SCALE_ERROR",
                    f"title:{title_text}",
                    title_val,
                )
            else:
                return (
                    "TRUSTED_EXISTING",
                    "EXPLICIT_TITLE_PRICE_MATCHES_CLEAN_VALUE",
                    f"title:{title_text}",
                    title_val,
                )
        else:
            return (
                "TRUSTED_REPARSED",
                "EXPLICIT_TITLE_PRICE_PARSED",
                f"title:{title_text}",
                title_val,
            )

    # If title has no explicit price, check clean_num and raw evidence
    if clean_num is None:
        return ("MISSING", "NO_CLEAN_PRICE", "", None)

    # Lexically small dot-grouped monthly amounts such as "13.000 đồng/tháng"
    # are ambiguous in rental feeds: they may be malformed million shorthand or
    # a non-rent charge. This is an evidence-form rule, not a numeric cutoff.
    if re.fullmatch(r"\s*\d{1,2}[\.,]000(?:\s*(?:vnđ|vnd|đồng|đ))?(?:\s*/\s*tháng)?\s*", raw_lower):
        return (
            "SUSPECT_UNIT_SCALE",
            "AMBIGUOUS_DOT_GROUPED_MONTHLY_AMOUNT",
            f"price_raw:{raw_str}",
            None,
        )

    # K3. Check if raw price indicates an unresolvable scale mismatch or ordinary unit monthly billion typo
    ordinary_unit_evidence = rental_scope == "SINGLE_OR_ORDINARY_UNIT" or bool(
        re.search(r"\b(?:phòng|gác|ở\s+ghép|ký\s+túc\s+xá|ktx)\b", title_lower)
    )
    if ordinary_unit_evidence and "tỷ" in raw_lower:
            return (
                "SUSPECT_UNIT_SCALE",
                "ORDINARY_UNIT_MONTHLY_BILLION_ANOMALY",
                f"price_raw:{raw_str}",
                None,
            )

    # K4. PARSER DISAGREEMENT
    if price_parser_comparison_status == "DISAGREEMENT":
        return (
            "PARSER_DISAGREEMENT_REVIEW",
            "EXISTING_AND_REPARSED_PRICE_DISAGREE",
            f"price_raw:{raw_str}",
            None,
        )

    # K5. Missing raw text evidence
    if not raw_str or raw_str.strip() == "" or raw_lower in ["none", "null", "nan"]:
        return (
            "INSUFFICIENT_EVIDENCE",
            "NO_RAW_PRICE_TEXT_EVIDENCE",
            "",
            None,
        )

    # K6. TRUSTED EXISTING
    if (
        price_quality_status == "VALIDATED_EXISTING"
        and price_lineage_aligned
        and price_parser_comparison_status == "MATCH"
    ):
        return (
            "TRUSTED_EXISTING",
            "ALIGNED_RAW_PRICE_MATCH",
            f"price_raw:{raw_str}",
            clean_num,
        )

    # K7. TRUSTED REPARSED from aligned raw evidence
    if (
        price_quality_status == "REPARSE_ACCEPTED_CLEAN"
        and price_lineage_aligned
    ):
        return (
            "TRUSTED_REPARSED",
            "ALIGNED_SAFE_RAW_REPARSE",
            f"price_raw:{raw_str}",
            clean_num,
        )

    # Default: INSUFFICIENT EVIDENCE
    return (
        "INSUFFICIENT_EVIDENCE",
        "NO_INDEPENDENT_NUMERIC_CONFIRMATION",
        f"price_raw:{raw_str}" if raw_str else "",
        None,
    )


def evaluate_price_model_suitability(
    model_value: Optional[float | Decimal],
    trust_status: str,
    title: Optional[str],
    listing_intent: Optional[str],
    rental_scope: Optional[str],
    statistical_outlier: bool,
    clean_area: Optional[float | Decimal] = None,
) -> tuple[str, str, str]:
    """Separate business suitability from parser/lineage trust.

    Magnitude is never sufficient for rejection. A statistical outlier is
    reviewed only when ordinary-room semantics are present and the title lacks
    independent, explicit monthly-rent evidence for the same value, or when
    cross-field semantic contradiction is detected between rent scale and unit
    size/type.
    """
    if trust_status not in {"TRUSTED_EXISTING", "TRUSTED_REPARSED"} or model_value is None or pd.isna(model_value):
        return "UNSUPPORTED_LINEAGE", "REVIEW", f"lineage:{trust_status}"
    if listing_intent in {"SALE", "TRANSFER"} or rental_scope in {"WHOLE_BUILDING", "MULTI_UNIT_BUSINESS"}:
        reason = listing_intent if listing_intent in {"SALE", "TRANSFER"} else rental_scope
        return "INCOMPATIBLE_LISTING_SEMANTICS", "EXCLUDED", f"semantic:{reason}"

    v = float(model_value)
    title_text = "" if title is None or pd.isna(title) else str(title)
    normalized = unicodedata.normalize("NFC", title_text.casefold())
    title_candidate = parse_rental_price_evidence_candidate(title_text, source_field="title")
    explicit_monthly_match = bool(
        title_candidate
        and title_candidate.role == "RENT_PRICE"
        and title_candidate.cadence == "MONTHLY_COMPATIBLE"
        and float(title_candidate.parsed_value) == v
    )
    ordinary_room_context = bool(
        re.search(
            r"\b(?:phòng\s+trọ|phong\s+tro|phòng|phong|nhà\s+trọ|nha\s+tro|ở\s+ghép|o\s+ghep|ký\s+túc\s+xá|ky\s+tuc\s+xa|ktx|sleepbox|dorm|cbcnv|sinh\s+viên|sinh\s+vien|sv|nữ\s+ở|nu\s+o|nam\s+ở|gác\s+lửng|gác|gac)\b",
            normalized,
        )
    )
    ordinary_scope = rental_scope in {"SINGLE_OR_ORDINARY_UNIT", "UNKNOWN"}
    has_luxury_or_commercial = bool(
        re.search(
            r"\b(?:villa|biệt\s+thự|biet\s+thu|penthouse|shophouse|tòa\s+nhà|toa\s+nha|mặt\s+bằng|mat\s+bang|kinh\s+doanh|văn\s+phòng|van\s+phong|khách\s+sạn|hotel|resort|căn\s+hộ\s+cao\s+cấp|can\s+ho\s+cao\s+cap|panorama|empire\s+city|metropole|vinhomes|masteri)\b",
            normalized,
        )
    )

    area_num = None
    if clean_area is not None and not pd.isna(clean_area):
        try:
            area_num = float(clean_area)
        except (ValueError, TypeError):
            pass

    # Cross-field contradiction: ordinary/small unit with extreme monthly rent without luxury/commercial corroboration
    if v >= 50_000_000 and not has_luxury_or_commercial and not explicit_monthly_match:
        if area_num is not None and area_num <= 40.0:
            return (
                "CROSS_FIELD_CONTRADICTION",
                "REVIEW",
                f"extreme_price_small_area_contradiction:price={v:,.0f},area={area_num}",
            )
        if ordinary_room_context and (area_num is None or area_num <= 60.0):
            return (
                "CROSS_FIELD_CONTRADICTION",
                "REVIEW",
                f"extreme_price_ordinary_room_contradiction:price={v:,.0f},area={area_num}",
            )
        if v >= 100_000_000 and ordinary_scope and (area_num is None or area_num < 50.0):
            return (
                "CROSS_FIELD_CONTRADICTION",
                "REVIEW",
                f"extreme_price_ordinary_scope_contradiction:price={v:,.0f},area={area_num}",
            )

    if area_num is not None and area_num > 0 and ordinary_scope and not has_luxury_or_commercial and not explicit_monthly_match:
        price_per_sqm = v / area_num
        if price_per_sqm >= 1_500_000 and v >= 30_000_000:
            return (
                "CROSS_FIELD_CONTRADICTION",
                "REVIEW",
                f"extreme_price_per_area_contradiction:ppa={price_per_sqm:,.0f}VND/m2,price={v:,.0f},area={area_num}",
            )

    if statistical_outlier and ordinary_scope and ordinary_room_context and not explicit_monthly_match:
        return (
            "ORDINARY_UNIT_OUTLIER_UNCORROBORATED",
            "REVIEW",
            "statistical_outlier+ordinary_room+no_matching_title_monthly_rent",
        )
    evidence = f"title:{title_candidate.matched_text}" if explicit_monthly_match else f"lineage:{trust_status}"
    return "SUPPORTED_MONTHLY_RENT", "SUPPORTED", evidence

def parse_price(raw_text: Optional[str]) -> Optional[Decimal]:
    if pd.isna(raw_text):
        return None
        
    text = str(raw_text).lower().strip()
    
    if re.search(r'(thỏa thuận|thương lượng|liên hệ)', text):
        return None
        
    text = text.replace(',', '.')
    
    # Check for compound unit e.g., "11 tỷ 300 triệu"
    compound_match_ty = re.search(r'([\d\.]+)\s*(tỷ)\s+([\d\.]+)\s*(triệu|tr)', text)
    if compound_match_ty:
        try:
            billion_part = Decimal(compound_match_ty.group(1).replace('.', '')) * Decimal('1000000000')
            million_part = Decimal(compound_match_ty.group(3).replace('.', '')) * Decimal('1000000')
            return billion_part + million_part
        except InvalidOperation:
            pass

    # Check for compound unit e.g., "3 triệu 500 nghìn"
    compound_match_tr = re.search(r'([\d\.]+)\s*(triệu|tr)\s+([\d\.]+)\s*(nghìn|ngàn|k)', text)
    if compound_match_tr:
        try:
            million_part = Decimal(compound_match_tr.group(1).replace('.', '')) * Decimal('1000000')
            thousand_part = Decimal(compound_match_tr.group(3).replace('.', '')) * Decimal('1000')
            return million_part + thousand_part
        except InvalidOperation:
            pass

    # Basic match
    match = re.search(r'([\d\.]+)\s*(triệu|tr|tỷ|nghìn|ngàn|k|vnđ|vnd|đồng)?', text)
    if not match:
        return None
        
    num_str = match.group(1)
    unit = match.group(2)
    
    # Handle multiple dots or thousand separators
    if num_str.count('.') > 1 or (num_str.count('.') == 1 and len(num_str.split('.')[-1]) == 3):
        num_str = num_str.replace('.', '')
        
    try:
        val = Decimal(num_str)
    except InvalidOperation:
        return None
        
    if unit in ['triệu', 'tr']:
        val = val * Decimal('1000000')
    elif unit == 'tỷ':
        val = val * Decimal('1000000000')
    elif unit in ['nghìn', 'ngàn', 'k']:
        val = val * Decimal('1000')
    elif unit in ['vnđ', 'vnd', 'đồng']:
        pass
        
    return val

_AREA_NUMBER = r"\d+(?:[\.,]\d+)?"
_EXPLICIT_AREA = re.compile(
    rf"(?P<value>{_AREA_NUMBER})\s*(?:m\s*(?:2|\^\s*2|²)|mét\s+vuông)\b",
    re.IGNORECASE,
)
_DIMENSIONS = [
    re.compile(
        rf"(?P<width>{_AREA_NUMBER})\s*m?\s*[x×]\s*(?P<length>{_AREA_NUMBER})\s*m\b",
        re.IGNORECASE,
    ),
    re.compile(
        rf"\bngang\s*(?P<width>{_AREA_NUMBER})\s*m\s*(?:[,;\-]\s*)?"
        rf"(?:dài|sâu)\s*(?P<length>{_AREA_NUMBER})\s*m\b",
        re.IGNORECASE,
    ),
]
_SINGLE_LINEAR = re.compile(
    rf"\b(?:gác\s+cao|trần\s+cao|cao|ngang|rộng|dài|sâu)\s*"
    rf"(?P<value>{_AREA_NUMBER})\s*m\b",
    re.IGNORECASE,
)


def _area_decimal(value: str) -> Decimal:
    return Decimal(value.replace(",", "."))


def parse_area_evidence(raw_text: Optional[str]) -> AreaEvidence:
    """Parse area only from explicit square units, 2-D geometry, or a bare numeric field.

    A single measurement in metres is linear evidence and is deliberately not
    converted to square metres. Bare numbers remain supported because several
    source fields carry a canonical numeric area without a unit.
    """
    if raw_text is None or pd.isna(raw_text):
        return AreaEvidence(None, "MISSING")
    text = unicodedata.normalize("NFC", str(raw_text).casefold()).strip()
    if not text or re.search(r"(?:liên hệ|chưa rõ|thỏa thuận)", text):
        return AreaEvidence(None, "MISSING")

    for pattern in _DIMENSIONS:
        match = pattern.search(text)
        if match:
            try:
                value = _area_decimal(match.group("width")) * _area_decimal(match.group("length"))
            except InvalidOperation:
                return AreaEvidence(None, "INVALID")
            return AreaEvidence(value, "DERIVED_FROM_DIMENSIONS", match.group(0))

    explicit = _EXPLICIT_AREA.search(text)
    if explicit:
        try:
            return AreaEvidence(_area_decimal(explicit.group("value")), "EXPLICIT_AREA", explicit.group(0))
        except InvalidOperation:
            return AreaEvidence(None, "INVALID")

    linear = _SINGLE_LINEAR.search(text)
    if linear:
        return AreaEvidence(None, "INSUFFICIENT_LINEAR_MEASUREMENT", linear.group(0))

    if re.fullmatch(_AREA_NUMBER, text):
        try:
            return AreaEvidence(_area_decimal(text), "EXISTING_NUMERIC", text)
        except InvalidOperation:
            return AreaEvidence(None, "INVALID")
    return AreaEvidence(None, "INSUFFICIENT_EVIDENCE")


def parse_area(raw_text: Optional[str]) -> Optional[Decimal]:
    return parse_area_evidence(raw_text).value


def evaluate_area_model_suitability(
    clean_area: Optional[float | Decimal],
    area_quality_status: str,
    raw_area: Optional[str],
    title: Optional[str],
) -> tuple[str, str, str]:
    """Return semantic status, model suitability, and auditable evidence."""
    if clean_area is None or pd.isna(clean_area) or area_quality_status == "MISSING_OR_REVIEW":
        return "INSUFFICIENT_EVIDENCE", "REVIEW", ""
    value = Decimal(str(clean_area))
    raw = parse_area_evidence(raw_area)
    title_evidence = parse_area_evidence(title)
    title_text = "" if title is None or pd.isna(title) else str(title)
    linear = _SINGLE_LINEAR.search(unicodedata.normalize("NFC", title_text.casefold()))
    if linear and title_evidence.value is None:
        try:
            linear_value = _area_decimal(linear.group("value"))
        except InvalidOperation:
            linear_value = None
        if linear_value == value:
            return "LINEAR_MEASUREMENT_CONTRADICTION", "REVIEW", f"title:{linear.group(0)}"
    raw_text = "" if raw_area is None or pd.isna(raw_area) else str(raw_area).strip()
    if (
        area_quality_status == "REPARSE_ACCEPTED_CLEAN"
        and re.fullmatch(r"\d{6,}\s*m\s*2", raw_text, flags=re.IGNORECASE)
        and title_evidence.value != value
    ):
        return "CURRENCY_SHAPED_AREA_EVIDENCE", "REVIEW", f"area_raw:{raw_text}"
    if title_evidence.value == value:
        return title_evidence.status, "SUPPORTED", f"title:{title_evidence.matched_text}"
    if raw.value == value:
        return raw.status, "SUPPORTED", f"area_raw:{raw.matched_text}"
    return "SUPPORTED_EXISTING_NUMERIC", "SUPPORTED", f"area_value:{value}"

def validate_price(val: Optional[Decimal]) -> str:
    """
    Returns: 'ACCEPTED_CLEAN', 'DOMAIN_INVALID', 'SUSPICIOUS'
    """
    if val is None: return 'DOMAIN_INVALID'
    if val <= 0: return 'DOMAIN_INVALID'
    if val < Decimal('10000'): return 'SUSPICIOUS' # E.g. "4 đồng" -> 4 -> SUSPICIOUS
    return 'ACCEPTED_CLEAN'

def validate_area(val: Optional[Decimal]) -> str:
    if val is None: return 'DOMAIN_INVALID'
    if val <= 0: return 'DOMAIN_INVALID'
    return 'ACCEPTED_CLEAN'

def classify_null_semantics(raw: Any) -> str:
    if pd.isna(raw) and not isinstance(raw, str):
        return 'PHYSICAL_NULL'
    text = str(raw)
    if text == "nan":
        return 'LITERAL_NAN_STRING'
    if text == "":
        return 'EMPTY_STRING'
    if text.strip() == "":
        return 'WHITESPACE_ONLY'
    return 'RAW_PRESENT'

def classify_price_raw_semantic(raw: Any, existing: Any) -> str:
    null_class = classify_null_semantics(raw)
    if null_class != 'RAW_PRESENT':
        return null_class
        
    text = str(raw).lower().strip()
    if re.search(r'(thỏa thuận|thương lượng|liên hệ)', text):
        return 'NEGOTIABLE_NON_NUMERIC'
        
    if re.search(r'\d', text):
        return 'RAW_PRESENT_NUMERIC_PARSE_FAILED'
        
    return 'RAW_PRESENT_NON_NUMERIC_SEMANTIC'

def classify_area_raw_semantic(raw: Any, existing: Any) -> str:
    null_class = classify_null_semantics(raw)
    if null_class != 'RAW_PRESENT':
        return null_class
        
    text = str(raw).lower().strip()
    if re.search(r'(liên hệ|chưa rõ|thỏa thuận)', text):
        return 'RAW_PRESENT_NON_NUMERIC'
        
    if re.search(r'\d', text):
        return 'RAW_PRESENT_NUMERIC_PARSE_FAILED'
        
    return 'UNCLASSIFIED'
    
def canonicalize_decimal(val: Any, scale: int) -> Optional[Decimal]:
    if pd.isna(val) or val is None:
        return None
    try:
        d = Decimal(str(val))
        return d.quantize(Decimal(f"1e-{scale}"), rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError):
        return None
