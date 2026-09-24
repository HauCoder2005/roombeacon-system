import re
import pandas as pd
from typing import Dict, Optional, Any

# Tokens
_PROVINCE_PATTERNS = [
    r"(?i)\b(?:thành phố hồ chí minh|tp\s*\.?\s*hcm|hcm|tphcm)\b",
    r"(?i)\b(?:thành phố hà nội|tp\s*\.?\s*hà nội|hà nội|hn)\b"
]

VN_CHARS = r"a-zA-ZàáãạảăắằẳẵặâấầẩẫậèéẹẻẽêềếểễệđìíĩỉịòóõọỏôốồổỗộơớờởỡợùúũụủưứừửữựỳỵỷỹýÀÁÃẠẢĂẮẰẲẴẶÂẤẦẨẪẬÈÉẸẺẼÊỀẾỂỄỆĐÌÍĨỈỊÒÓÕỌỎÔỐỒỔỖỘƠỚỜỞỠỢÙÚŨỤỦƯỨỪỬỮỰỲỴỶỸÝ"

def parse_address_text(address: str) -> Dict[str, Any]:
    """Parse a Vietnamese address into components deterministically."""
    if pd.isna(address) or not str(address).strip():
        return {
            'street_text_extracted': None,
            'ward_text_extracted': None,
            'district_text_extracted': None,
            'province_text_extracted': None,
            'parse_status': 'NO_ADDRESS_EVIDENCE'
        }
        
    text = str(address).strip()
    
    parts = [p.strip() for p in re.split(r'[,;-]', text) if p.strip()]
    
    components = {
        'street_text_extracted': None,
        'ward_text_extracted': None,
        'district_text_extracted': None,
        'province_text_extracted': None,
    }
    
    # 1. Province
    for p in _PROVINCE_PATTERNS:
        if re.search(p, text):
            components['province_text_extracted'] = re.search(p, text).group(0).strip()
            break
            
    # 2. Extract District
    district_match = None
    for part in parts:
        if re.search(fr'(?i)^(quận|huyện|thành phố thủ đức|tp\s*\.?\s*thủ đức)', part):
            district_match = part
            break
        m = re.match(r'(?i)^Q(?:\s*\.\s*|\s+)?(\d+|[a-zA-Z\s]+)$', part)
        if m:
            district_match = f"Quận {m.group(1).strip()}"
            break
            
    if not district_match:
        dm = re.search(fr"(?i)\b(quận\s+\d+|quận\s+[{VN_CHARS}\s\d]+|huyện\s+[{VN_CHARS}\s\d]+|thành phố thủ đức|tp\s*\.?\s*thủ đức)(?=\s*,|\s*-|\s*$)", text)
        if dm: district_match = dm.group(1).strip()
        else:
            dm_abbr = re.search(r"(?i)\bQ(?:\s*\.\s*|\s+)?(\d+|[a-zA-Z\s]+)(?=\s*,|\s*-|\s*$)", text)
            if dm_abbr: district_match = f"Quận {dm_abbr.group(1).strip()}"
            
    components['district_text_extracted'] = district_match
    
    # 3. Extract Ward
    ward_match = None
    for part in parts:
        if re.search(r'(?i)^(phường|xã|thị trấn)', part):
            ward_match = part
            break
        m = re.match(r'(?i)^P(?:\s*\.\s*|\s+)?(\d+|[a-zA-Z\s]+)$', part)
        if m:
            ward_match = f"Phường {m.group(1).strip()}"
            break
            
    if not ward_match:
        wm = re.search(fr"(?i)\b(phường\s+\d+|phường\s+[{VN_CHARS}\s\d]+|xã\s+[{VN_CHARS}\s\d]+|thị trấn\s+[{VN_CHARS}\s\d]+)(?=\s*,|\s*-|\s*$)", text)
        if wm: ward_match = wm.group(1).strip()
        else:
            wm_abbr = re.search(r"(?i)\bP(?:\s*\.\s*|\s+)?(\d+|[a-zA-Z\s]+)(?=\s*,|\s*-|\s*$)", text)
            if wm_abbr: ward_match = f"Phường {wm_abbr.group(1).strip()}"
            
    components['ward_text_extracted'] = ward_match

    # 4. Extract Street
    street_match = None
    for part in parts:
        if re.search(r'(?i)^(đường|phố|hẻm)', part):
            street_match = part
            break
    if not street_match:
        sm = re.search(fr"(?i)\b(đường\s+[{VN_CHARS}\s\d/]+|phố\s+[{VN_CHARS}\s\d/]+|hẻm\s+[{VN_CHARS}\s\d/]+)(?=\s*,|\s*-)", text)
        if sm: street_match = sm.group(1).strip()
        
    components['street_text_extracted'] = street_match
    
    # Determine Status
    found_count = sum(1 for v in components.values() if v is not None)
    if found_count >= 3:
        status = 'PARSED'
    elif found_count > 0:
        status = 'PARTIALLY_PARSED'
    else:
        status = 'UNRECOGNIZED_FORMAT'
        
    # Ambiguity check (e.g. multiple wards matching)
    if found_count > 0:
        w_count = sum(1 for p in parts if re.search(r'(?i)^(phường|xã|p\.)', p))
        d_count = sum(1 for p in parts if re.search(r'(?i)^(quận|huyện|q\.)', p))
        if w_count > 1 or d_count > 1:
            status = 'AMBIGUOUS'
            
    components['parse_status'] = status
    return components

def apply_address_parsing(df: pd.DataFrame, source_col: str, prefix: str = '') -> pd.DataFrame:
    result = df.copy(deep=False)
    parsed = result[source_col].apply(parse_address_text)
    
    parsed_df = pd.DataFrame(parsed.tolist(), index=result.index)
    if prefix:
        parsed_df = parsed_df.add_prefix(prefix)
        
    for col in parsed_df.columns:
        result[col] = parsed_df[col]
        
    return result
