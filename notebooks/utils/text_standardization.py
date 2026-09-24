import pandas as pd
import unicodedata
import re

def normalize_unicode(text: str) -> str:
    """Normalize Unicode to NFC form if it's a valid string."""
    if pd.isna(text) or not isinstance(text, str):
        return text
    return unicodedata.normalize('NFC', text)

def normalize_whitespace(text: str) -> str:
    """Trim leading/trailing whitespaces and collapse repeated spaces to single space."""
    if pd.isna(text) or not isinstance(text, str):
        return text
    # Strip leading/trailing whitespaces, then collapse intermediate spaces
    # We do NOT remove line breaks \n blindly, only spaces \s+ that match space/tabs.
    # To be safe and just collapse horizontal spaces:
    text = text.strip()
    return re.sub(r'[ \t\r]+', ' ', text)

def apply_text_standardization(
    df: pd.DataFrame, 
    source_col: str, 
    target_col: str,
    do_unicode: bool = True,
    do_whitespace: bool = True
) -> pd.DataFrame:
    """Apply safe, non-destructive text standardization."""
    result = df.copy(deep=False)
    
    # Check if empty strings exist to map to None
    series = result[source_col].replace(r'^\s*$', None, regex=True)
    
    if do_unicode:
        series = series.apply(normalize_unicode)
    if do_whitespace:
        series = series.apply(normalize_whitespace)
        
    result[target_col] = series
    return result

