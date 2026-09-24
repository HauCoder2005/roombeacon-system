import pytest
import sys
from decimal import Decimal
sys.path.append('.')
from notebooks.utils.price_area_validation import (
    parse_price, parse_area, validate_price, validate_area,
    canonicalize_decimal
)

@pytest.mark.parametrize("raw, expected", [
    ("11 tỷ 300 triệu", Decimal("11300000000")),
    ("1 tỷ 250 triệu", Decimal("1250000000")),
    ("4 triệu 400 nghìn", Decimal("4400000")),
    ("3 triệu 500 nghìn", Decimal("3500000")),
    ("Thỏa thuận", None),
    ("Thương lượng", None),
    ("4 đồng/tháng", Decimal("4")),
    (None, None),
    ("", None),
])
def test_parse_price(raw, expected):
    assert parse_price(raw) == expected

@pytest.mark.parametrize("raw, expected", [
    ("18.999", Decimal("18.999")),
    ("18.5", Decimal("18.5")),
    ("18,5", Decimal("18.5")),
    ("20 m2", Decimal("20")),
    ("20 m²", Decimal("20")),
    ("0", Decimal("0")),
    ("0 m2 0 PN 0 WC", Decimal("0")),
    ("Liên hệ", None),
    (None, None),
    ("", None),
])
def test_parse_area(raw, expected):
    assert parse_area(raw) == expected

def test_validation():
    assert validate_price(Decimal("4")) == "SUSPICIOUS"
    assert validate_price(Decimal("0")) == "DOMAIN_INVALID"
    assert validate_price(Decimal("3500000")) == "ACCEPTED_CLEAN"
    
    assert validate_area(Decimal("0")) == "DOMAIN_INVALID"
    assert validate_area(Decimal("18.5")) == "ACCEPTED_CLEAN"
    
def test_canonicalization():
    assert canonicalize_decimal("18.999", 2) == Decimal("19.00")
    assert canonicalize_decimal(19.0, 2) == Decimal("19.00")

