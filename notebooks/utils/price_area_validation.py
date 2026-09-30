import re
import pandas as pd
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Optional, Dict, Any, Tuple

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

def parse_area(raw_text: Optional[str]) -> Optional[Decimal]:
    if pd.isna(raw_text):
        return None
        
    text = str(raw_text).lower().strip()
    
    if re.search(r'(liên hệ|chưa rõ|thỏa thuận)', text):
        return None
        
    text = text.replace(',', '.')
    
    match = re.search(r'([\d\.]+)\s*(m2|m\^2|m²|mét|m\s*2)?', text)
    if not match:
        return None
        
    num_str = match.group(1)
    
    if num_str.count('.') > 1:
        num_str = num_str.replace('.', '', num_str.count('.') - 1)
        
    try:
        val = Decimal(num_str)
    except InvalidOperation:
        return None
        
    return val

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

