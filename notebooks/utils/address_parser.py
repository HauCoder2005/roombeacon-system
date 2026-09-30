import re
import pandas as pd
from typing import Dict, Optional, Any

_PROVINCE_PATTERNS = [
    r"(?i)\b(?:thành phố hồ chí minh|tp\s*\.?\s*hcm|hcm|tphcm)\b",
    r"(?i)\b(?:thành phố hà nội|tp\s*\.?\s*hà nội|hà nội|hn)\b"
]

VN_CHARS = r"a-zA-ZàáãạảăắằẳẵặâấầẩẫậèéẹẻẽêềếểễệđìíĩỉịòóõọỏôốồổỗộơớờởỡợùúũụủưứừửữựỳỵỷỹýÀÁÃẠẢĂẮẰẲẴẶÂẤẦẨẪẬÈÉẸẺẼÊỀẾỂỄỆĐÌÍĨỈỊÒÓÕỌỎÔỐỒỔỖỘƠỚỜỞỠỢÙÚŨỤỦƯỨỪỬỮỰỲỴỶỸÝ"

# --- GAZETTEER DEFINITIONS ---
# Gazetteer dùng để bắt các alias dị biệt, sửa lỗi nguồn viết sai, nuốt chữ.
HCM_DISTRICTS = {
    "Quận 1": ["Quận 1", "Q1", "Q.1", "Q. 1", "Quận 01"],
    "Quận 2": ["Quận 2", "Q2", "Q.2", "Q. 2", "Quận 02"],
    "Quận 3": ["Quận 3", "Q3", "Q.3", "Q. 3", "Quận 03"],
    "Quận 4": ["Quận 4", "Q4", "Q.4", "Q. 4", "Quận 04"],
    "Quận 5": ["Quận 5", "Q5", "Q.5", "Q. 5", "Quận 05"],
    "Quận 6": ["Quận 6", "Q6", "Q.6", "Q. 6", "Quận 06"],
    "Quận 7": ["Quận 7", "Q7", "Q.7", "Q. 7", "Quận 07"],
    "Quận 8": ["Quận 8", "Q8", "Q.8", "Q. 8", "Quận 08"],
    "Quận 9": ["Quận 9", "Q9", "Q.9", "Q. 9", "Quận 09"],
    "Quận 10": ["Quận 10", "Q10", "Q.10", "Q. 10"],
    "Quận 11": ["Quận 11", "Q11", "Q.11", "Q. 11"],
    "Quận 12": ["Quận 12", "Q12", "Q.12", "Q. 12"],
    "Quận Bình Thạnh": ["Quận Bình Thạnh", "Q. Bình Thạnh", "Bình Thạnh", "Q Bình Thạnh", "Phường Bình Thạnh"],
    "Quận Gò Vấp": ["Quận Gò Vấp", "Q. Gò Vấp", "Gò Vấp", "Phường Gò Vấp"],
    "Quận Tân Bình": ["Quận Tân Bình", "Q. Tân Bình", "Tân Bình", "Phường Tân Bình"],
    "Quận Tân Phú": ["Quận Tân Phú", "Q. Tân Phú", "Tân Phú", "Phường Tân Phú"],
    "Quận Phú Nhuận": ["Quận Phú Nhuận", "Q. Phú Nhuận", "Phú Nhuận", "Phường Phú Nhuận"],
    "Quận Bình Tân": ["Quận Bình Tân", "Q. Bình Tân", "Bình Tân", "Phường Bình Tân"],
    "Thành phố Thủ Đức": ["Thành phố Thủ Đức", "TP Thủ Đức", "TP. Thủ Đức", "Thủ Đức", "Quận Thủ Đức", "Phường Thủ Đức"],
    "Huyện Củ Chi": ["Huyện Củ Chi", "Củ Chi", "H. Củ Chi"],
    "Huyện Hóc Môn": ["Huyện Hóc Môn", "Hóc Môn", "H. Hóc Môn"],
    "Huyện Bình Chánh": ["Huyện Bình Chánh", "Bình Chánh", "H. Bình Chánh"],
    "Huyện Nhà Bè": ["Huyện Nhà Bè", "Nhà Bè", "H. Nhà Bè"],
    "Huyện Cần Giờ": ["Huyện Cần Giờ", "Cần Giờ", "H. Cần Giờ"]
}

HCM_WARDS = {
    "Quận Bình Thạnh": {
        "Phường 27": ["Phường 27", "Thạnh Mỹ Tây", "Phường Thạnh Mỹ Tây"],
        "Phường 28": ["Phường 28", "Thanh Đa", "Bán đảo Thanh Đa"],
        "Phường 13": ["Phường 13", "Bình Lợi", "Bình Lợi Trung"],
        "Phường 1": ["Phường 1", "Gia Định", "Phường Gia Định"]
    },
    "Quận Gò Vấp": {
        "Phường 6": ["Phường 6", "An Nhơn", "Phường An Nhơn"],
        "Phường 8": ["Phường 8", "Thông Tây Hội", "Phường Thông Tây Hội"],
        "Phường 14": ["Phường 14", "An Hội", "An Hội Tây", "Phường An Hội Tây"]
    },
    "Quận Tân Bình": {
        "Phường 7": ["Phường 7", "Bảy Hiền", "Ngã tư Bảy Hiền", "Phường Bảy Hiền"]
    },
    "Thành phố Thủ Đức": {
        "Phường Hiệp Bình Chánh": ["Hiệp Bình", "Phường Hiệp Bình", "Hiệp Bình Chánh"],
        "Phường Tam Bình": ["Tam Bình", "Phường Tam Bình"],
        "Phường Tăng Nhơn Phú A": ["Tăng Nhơn Phú", "Phường Tăng Nhơn Phú"]
    },
    "Quận 1": {
        "Phường Cầu Ông Lãnh": ["Cầu Ông Lãnh", "Phường Cầu Ông Lãnh"],
        "Phường Bến Thành": ["Bến Thành", "Phường Bến Thành"]
    },
    "Quận 5": {
        "Phường 1": ["Chợ Quán", "Phường Chợ Quán"]
    },
    "Quận 8": {
        "Phường 4": ["Chánh Hưng", "Phường Chánh Hưng"]
    },
    "Quận 10": {
        "Phường 12": ["Hòa Hưng", "Phường Hòa Hưng"]
    },
    "Quận Tân Phú": {
        "Phường Tân Sơn Nhì": ["Tân Sơn Nhì", "Phường Tân Sơn Nhì"],
        "Phường Tây Thạnh": ["Tây Thạnh", "Phường Tây Thạnh"]
    },
    "Quận 7": {
        "Phường Tân Thuận Đông": ["Tân Thuận", "Phường Tân Thuận", "Tân Thuận Đông"],
        "Phường Tân Hưng": ["Tân Hưng", "Phường Tân Hưng"]
    }
}

from notebooks.enums.ward_gazetteer import MERGED_WARDS

class FullTextGazetteer:
    """Aho-Corasick equivalent using sorted regex alternation for maximal munch."""
    def __init__(self):
        self.mapping = {}
        self.pattern = None
        
    def add_keyword(self, keyword: str, entity_type: str, standard_name: str, parent: str = None):
        self.mapping[keyword.lower()] = {
            'type': entity_type,
            'name': standard_name,
            'parent': parent
        }
        
    def build(self):
        keywords = sorted(self.mapping.keys(), key=len, reverse=True)
        escaped = [re.escape(k) for k in keywords]
        self.pattern = re.compile(r'(?i)\b(' + '|'.join(escaped) + r')\b')
        
    def extract(self, text: str):
        if not self.pattern:
            self.build()
        matches = self.pattern.finditer(text)
        results = []
        for match in matches:
            kw = match.group(1).lower()
            results.append(self.mapping[kw])
        return results

gz = FullTextGazetteer()

for dist_name, aliases in HCM_DISTRICTS.items():
    for alias in aliases:
        gz.add_keyword(alias, 'DISTRICT', dist_name)
        
for dist_name, wards in HCM_WARDS.items():
    for ward_name, aliases in wards.items():
        for alias in aliases:
            gz.add_keyword(alias, 'WARD', ward_name, parent=dist_name)


for new_ward, data in MERGED_WARDS.items():
    dist_name = data["district"] if data["district"] != "UNKNOWN_DISTRICT" else None
    for alias in data["aliases"]:
        gz.add_keyword(alias, 'WARD', new_ward, parent=dist_name)

gz.build()
# -----------------------------

def parse_address_text(address: str) -> Dict[str, Any]:
    """Parse a Vietnamese address using Gazetteer combined with regex fallback."""
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
            
    # 2. Gazetteer Extraction (Prioritized for tricky formats)
    entities = gz.extract(text)
    
    for ent in entities:
        if ent['type'] == 'WARD' and not components['ward_text_extracted']:
            components['ward_text_extracted'] = ent['name']
            components['district_text_extracted'] = ent['parent']
        elif ent['type'] == 'DISTRICT' and not components['district_text_extracted']:
            components['district_text_extracted'] = ent['name']

    # 3. Fallback Regex for District if Gazetteer missed it
    if not components['district_text_extracted']:
        for part in parts:
            if re.search(fr'(?i)^(quận|huyện|thành phố thủ đức|tp\s*\.?\s*thủ đức)', part):
                components['district_text_extracted'] = part
                break
            m = re.match(r'(?i)^Q(?:\s*\.\s*|\s+)?(\d+|[a-zA-Z\s]+)$', part)
            if m:
                components['district_text_extracted'] = f"Quận {m.group(1).strip()}"
                break
        
        if not components['district_text_extracted']:
            dm = re.search(fr"(?i)\b(quận\s+\d+|quận\s+[{VN_CHARS}\s\d]+|huyện\s+[{VN_CHARS}\s\d]+)(?=\s*,|\s*-|\s*$)", text)
            if dm: components['district_text_extracted'] = dm.group(1).strip()
            else:
                dm_abbr = re.search(r"(?i)\bQ(?:\s*\.\s*|\s+)?(\d+|[a-zA-Z\s]+)(?=\s*,|\s*-|\s*$)", text)
                if dm_abbr: components['district_text_extracted'] = f"Quận {dm_abbr.group(1).strip()}"

    # 4. Fallback Regex for Ward if Gazetteer missed it
    if not components['ward_text_extracted']:
        # IMPORTANT: Avoid matching districts as wards (e.g., if a district was mapped to "Phường Gò Vấp", it's already caught by Gazetteer above)
        for part in parts:
            if re.search(r'(?i)^(phường|xã|thị trấn)', part):
                # Ensure we don't accidentally catch a district name here (Gò Vấp, Tân Bình, v.v.)
                dist_check = re.search(r'(?i)\b(gò vấp|bình thạnh|tân bình|tân phú|bình tân|phú nhuận|thủ đức)\b', part)
                if not dist_check:
                    components['ward_text_extracted'] = part
                    break
            m = re.match(r'(?i)^P(?:\s*\.\s*|\s+)?(\d+|[a-zA-Z\s]+)$', part)
            if m:
                components['ward_text_extracted'] = f"Phường {m.group(1).strip()}"
                break
                
        if not components['ward_text_extracted']:
            wm = re.search(fr"(?i)\b(phường\s+\d+|phường\s+[{VN_CHARS}\s\d]+|xã\s+[{VN_CHARS}\s\d]+|thị trấn\s+[{VN_CHARS}\s\d]+)(?=\s*,|\s*-|\s*$)", text)
            if wm: 
                dist_check = re.search(r'(?i)\b(gò vấp|bình thạnh|tân bình|tân phú|bình tân|phú nhuận|thủ đức)\b', wm.group(1))
                if not dist_check:
                    components['ward_text_extracted'] = wm.group(1).strip()

    # 5. Extract Street
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
