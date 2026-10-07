import pytest
import sys
import pandas as pd
sys.path.append('.')
from notebooks.utils.address_parser import parse_address_text, apply_address_parsing

def test_null_and_empty():
    res1 = parse_address_text(None)
    assert res1['parse_status'] == 'NO_ADDRESS_EVIDENCE'
    
    res2 = parse_address_text("")
    assert res2['parse_status'] == 'NO_ADDRESS_EVIDENCE'
    
    res3 = parse_address_text("   ")
    assert res3['parse_status'] == 'NO_ADDRESS_EVIDENCE'

def test_full_address():
    res = parse_address_text("Đường Tô Hiến Thành, Phường 14, Quận 10, TP.HCM")
    assert res['street_text_extracted'] == 'Đường Tô Hiến Thành'
    assert res['ward_text_extracted'] == 'Phường 14'
    assert res['district_text_extracted'] == 'Quận 10'
    assert res['province_text_extracted'] == 'TP.HCM'
    assert res['parse_status'] == 'PARSED'

def test_ward_district():
    res = parse_address_text("Phường Tân Định, Quận 1")
    assert res['ward_text_extracted'] == 'Phường Tân Định'
    assert res['district_text_extracted'] == 'Quận 1'
    assert res['parse_status'] == 'PARTIALLY_PARSED'

def test_district_only():
    res = parse_address_text("Quận 1")
    assert res['district_text_extracted'] == 'Quận 1'
    assert res['parse_status'] == 'PARTIALLY_PARSED'

def test_province_only():
    res = parse_address_text("TPHCM")
    assert res['province_text_extracted'] == 'TPHCM'
    assert res['parse_status'] == 'PARTIALLY_PARSED'

def test_abbreviations():
    res = parse_address_text("P. 5, Q. 3, HCM")
    assert res['ward_text_extracted'] == 'Phường 5'
    assert res['district_text_extracted'] == 'Quận 3'
    assert res['province_text_extracted'] == 'HCM'

def test_xa_huyen():
    res = parse_address_text("Xã Phước Kiển, Huyện Nhà Bè")
    assert res['ward_text_extracted'] == 'Xã Phước Kiển'
    assert res['district_text_extracted'] == 'Huyện Nhà Bè'

def test_ambiguous():
    res = parse_address_text("Phường 5, Phường 6, Quận 10")
    assert res['parse_status'] == 'AMBIGUOUS'

def test_unrecognized():
    res = parse_address_text("Chung cư Sunrise City")
    assert res['parse_status'] == 'UNRECOGNIZED_FORMAT'

def test_deterministic():
    res1 = parse_address_text("Đường A, Phường B, Quận C")
    res2 = parse_address_text("Đường A, Phường B, Quận C")
    assert res1 == res2

def test_apply_address_parsing():
    df = pd.DataFrame({'addr': ['Quận 1', 'Phường 2, Quận 3']})
    res_df = apply_address_parsing(df, 'addr')
    assert 'district_text_extracted' in res_df.columns
    assert res_df.loc[0, 'district_text_extracted'] == 'Quận 1'
    assert res_df.loc[1, 'ward_text_extracted'] == 'Phường 2'


def test_quang_trung_not_misparsed_as_quan_uang():
    res1 = parse_address_text("Đường Quang Trung, Phường 8, Gò Vấp")
    assert res1["district_text_extracted"] != "Quận uang Trung"
    assert res1["district_text_extracted"] != "Quận uang"
    assert res1["district_text_extracted"] == "Quận Gò Vấp"
    assert res1["ward_text_extracted"] == "Phường 8"
    assert res1["street_text_extracted"] == "Đường Quang Trung"

    res2 = parse_address_text("Quang Trung, Gò Vấp")
    assert res2["district_text_extracted"] != "Quận uang Trung"
    assert res2["district_text_extracted"] != "Quận uang"
    assert res2["district_text_extracted"] == "Quận Gò Vấp"

    res3 = parse_address_text("Đường Nguyễn Oanh")
    assert res3["district_text_extracted"] is None
    assert res3["street_text_extracted"] == "Đường Nguyễn Oanh"

    res4 = parse_address_text("123 Đường Quang Trung, Phường 10, Gò Vấp")
    assert res4["district_text_extracted"] == "Quận Gò Vấp"
    assert res4["ward_text_extracted"] == "Phường 10"
    assert res4["street_text_extracted"] == "Đường Quang Trung"


def test_valid_q_abbreviations_still_work():
    cases = {
        "Q.1": "Quận 1",
        "Q1": "Quận 1",
        "Q. 10": "Quận 10",
        "Quận 7": "Quận 7",
        "Q. Tân Bình": "Quận Tân Bình",
        "Q.Bình Thạnh": "Quận Bình Thạnh",
        "Q Bình Thạnh": "Quận Bình Thạnh",
    }
    for text, expected in cases.items():
        res = parse_address_text(text)
        assert res["district_text_extracted"] == expected, f"Failed for {text}: got {res['district_text_extracted']}"

