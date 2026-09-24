import pytest
import sys
import pandas as pd
sys.path.append('.')
from notebooks.utils.ward_normalization import map_ward, normalize_ward_text

def test_null_missing():
    res = map_ward(None, None)
    assert res['ward_mapping_status'] == 'MISSING'

def test_unchanged():
    res = map_ward("Phường Bến Thành", "Quận 1")
    assert res['ward_mapping_status'] == 'UNCHANGED'
    assert res['ward_current'] == 'Phường Bến Thành'

def test_mapped():
    res = map_ward("Phường 14", "Quận Gò Vấp")
    assert res['ward_mapping_status'] == 'MAPPED'
    assert res['ward_current'] == 'Phường An Hội Tây'

def test_ambiguous():
    res = map_ward("Phường 15", "Quận Tân Bình")
    assert res['ward_mapping_status'] == 'AMBIGUOUS'
    assert res['ward_current'] is None
    assert "Phường Tân Bình" in res['ward_mapping_candidates']

def test_unmapped():
    res = map_ward("Phường XYZ", "Quận 1")
    assert res['ward_mapping_status'] == 'UNMAPPED'
    assert res['ward_current'] is None

def test_abbreviation_norm():
    assert normalize_ward_text("P. 5") == "Phường 5"
    assert normalize_ward_text("X. Bình Hưng") == "Xã Bình Hưng"
    assert normalize_ward_text("TT. Nhà Bè") == "Thị trấn Nhà Bè"

def test_with_phuong_number_prefix_key():
    # In WARD_MAPPING there's "1 quan binh thanh" -> Phường Gia Định
    # Let's test if we pass "Phường 1", "Quận Bình Thạnh", it maps correctly
    res = map_ward("Phường 1", "Quận Bình Thạnh")
    assert res['ward_mapping_status'] == 'MAPPED'
    assert res['ward_current'] == 'Phường Gia Định'

