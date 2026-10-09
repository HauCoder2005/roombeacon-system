import pytest
import sys
from decimal import Decimal
sys.path.append('.')
from notebooks.utils.price_area_validation import (
    parse_price, parse_area, parse_area_evidence, validate_price, validate_area,
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


@pytest.mark.parametrize("raw", [
    "gác cao 2m",
    "trần cao 3m",
    "ngang 4m",
    "rộng 4m",
    "dài 10m",
])
def test_single_linear_measurement_is_not_area(raw):
    assert parse_area(raw) is None
    assert parse_area_evidence(raw).status == "INSUFFICIENT_LINEAR_MEASUREMENT"


@pytest.mark.parametrize("raw, expected", [
    ("4m x 7m", Decimal("28")),
    ("4 x 7m", Decimal("28")),
    ("ngang 4m dài 7m", Decimal("28")),
    ("1,3mx2m", Decimal("2.6")),
])
def test_two_dimensional_geometry_derives_area(raw, expected):
    evidence = parse_area_evidence(raw)
    assert evidence.value == expected
    assert evidence.status == "DERIVED_FROM_DIMENSIONS"


@pytest.mark.parametrize("raw, expected", [
    ("diện tích 20m2", Decimal("20")),
    ("20 m²", Decimal("20")),
    ("30 m 2", Decimal("30")),
])
def test_explicit_square_metres_are_area(raw, expected):
    evidence = parse_area_evidence(raw)
    assert evidence.value == expected
    assert evidence.status == "EXPLICIT_AREA"

def test_validation():
    assert validate_price(Decimal("4")) == "SUSPICIOUS"
    assert validate_price(Decimal("0")) == "DOMAIN_INVALID"
    assert validate_price(Decimal("3500000")) == "ACCEPTED_CLEAN"
    
    assert validate_area(Decimal("0")) == "DOMAIN_INVALID"
    assert validate_area(Decimal("18.5")) == "ACCEPTED_CLEAN"
    
def test_canonicalization():
    assert canonicalize_decimal("18.999", 2) == Decimal("19.00")
    assert canonicalize_decimal(19.0, 2) == Decimal("19.00")
