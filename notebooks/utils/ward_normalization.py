import re
import unicodedata
import pandas as pd
from typing import Dict, Any, List, Optional
import sys
sys.path.append('.')
from notebooks.enums.ward_mapping import WARD_MAPPING

def remove_vietnamese_accents(value: str) -> str:
    if not isinstance(value, str):
        return ""
    decomposed = unicodedata.normalize("NFD", value)
    without_marks = "".join(c for c in decomposed if unicodedata.category(c) != "Mn")
    return without_marks.replace("đ", "d").replace("Đ", "D")

def build_mapping_dict() -> Dict[str, List[str]]:
    """Build the dictionary with added compatibilities from previous normalizer."""
    mapping = dict(WARD_MAPPING)
    mapping["phuong 11 quan 10"] = ["Phường Hòa Hưng"]
    
    # Prepend "phuong" to numeric ward keys that end with "quan ..."
    # For example, "1 quan binh thanh" -> "phuong 1 quan binh thanh"
    _NUMERIC_WARD_CONTEXT_PATTERN = re.compile(r"^\d+\s+quan\b")
    
    final_mapping = {}
    for k, v in mapping.items():
        if _NUMERIC_WARD_CONTEXT_PATTERN.match(k):
            final_mapping[f"phuong {k}"] = v
        final_mapping[k] = v
        
    return final_mapping

_FINAL_MAPPING = build_mapping_dict()
_CURRENT_WARDS = set(w for wards in _FINAL_MAPPING.values() for w in wards)

def normalize_ward_text(ward_raw: Optional[str]) -> Optional[str]:
    """Normalize ward prefix and format."""
    if pd.isna(ward_raw) or not str(ward_raw).strip():
        return None
        
    text = str(ward_raw).strip()
    
    # Collapse whitespace
    text = re.sub(r'\s+', ' ', text)
    
    # Normalize prefixes: P. -> Phường, X. -> Xã, TT. -> Thị trấn
    text = re.sub(r'(?i)^P\s*\.\s*', 'Phường ', text)
    text = re.sub(r'(?i)^P\s+(?=\d)', 'Phường ', text)
    text = re.sub(r'(?i)^X\s*\.\s*', 'Xã ', text)
    text = re.sub(r'(?i)^X\s+(?=\w)', 'Xã ', text)
    text = re.sub(r'(?i)^TT\s*\.\s*', 'Thị trấn ', text)
    text = re.sub(r'(?i)^TT\s+(?=\w)', 'Thị trấn ', text)
    
    # Title case but preserve specific known forms if needed. Title is generally okay.
    return text.title().replace("Phường", "Phường").replace("Xã", "Xã").replace("Thị Trấn", "Thị trấn")

def clean_key(text: str) -> str:
    """Create accentless lower case lookup key."""
    if not text: return ""
    key = remove_vietnamese_accents(text).lower()
    key = re.sub(r'[^a-z0-9\s]', ' ', key)
    return re.sub(r'\s+', ' ', key).strip()

def map_ward(ward_extracted: Optional[str], district_extracted: Optional[str]) -> Dict[str, Any]:
    if pd.isna(ward_extracted) or not str(ward_extracted).strip():
        return {
            'ward_normalized': None,
            'ward_current': None,
            'ward_mapping_status': 'MISSING',
            'ward_mapping_candidates': []
        }
        
    ward_norm = normalize_ward_text(ward_extracted)
    
    # Check if already current
    # We should match exactly or case-insensitive? The set is Title Case.
    if ward_norm in _CURRENT_WARDS:
        return {
            'ward_normalized': ward_norm,
            'ward_current': ward_norm,
            'ward_mapping_status': 'UNCHANGED',
            'ward_mapping_candidates': [ward_norm]
        }
        
    ward_key = clean_key(ward_norm)
    dist_key = clean_key(district_extracted) if not pd.isna(district_extracted) else ""
    
    candidates = []
    
    # Strategy 1: Ward + District exact match
    if dist_key:
        # Sometimes district key has "quan", sometimes not.
        if not dist_key.startswith("quan ") and not dist_key.startswith("huyen "):
            pass # Keep as is
            
        combo_key = f"{ward_key} {dist_key}"
        if combo_key in _FINAL_MAPPING:
            candidates = _FINAL_MAPPING[combo_key]
            
    # Strategy 2: Ward exact match
    if not candidates and ward_key in _FINAL_MAPPING:
        candidates = _FINAL_MAPPING[ward_key]
        
    # Strategy 3: Remove "phuong" prefix from key and try again (e.g., if ward_key is "phuong 5" and dict has "5 quan ...")
    if not candidates and ward_key.startswith("phuong "):
        base_ward_key = ward_key[7:].strip()
        
        if dist_key:
            combo_key = f"{base_ward_key} {dist_key}"
            if combo_key in _FINAL_MAPPING:
                candidates = _FINAL_MAPPING[combo_key]
                
        if not candidates and base_ward_key in _FINAL_MAPPING:
            candidates = _FINAL_MAPPING[base_ward_key]
            
    status = 'UNMAPPED'
    ward_current = None
    
    if candidates:
        if len(candidates) == 1:
            status = 'MAPPED'
            ward_current = candidates[0]
        else:
            status = 'AMBIGUOUS'
            
    return {
        'ward_normalized': ward_norm,
        'ward_current': ward_current,
        'ward_mapping_status': status,
        'ward_mapping_candidates': candidates
    }

def apply_ward_mapping(df: pd.DataFrame, ward_col: str, dist_col: str) -> pd.DataFrame:
    result = df.copy(deep=False)
    
    def process_row(row):
        return map_ward(row[ward_col], row[dist_col])
        
    mapped = result.apply(process_row, axis=1)
    mapped_df = pd.DataFrame(mapped.tolist(), index=result.index)
    
    for col in mapped_df.columns:
        result[col] = mapped_df[col]
        
    return result

