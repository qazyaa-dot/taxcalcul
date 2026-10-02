"""한국어 금액 파싱, 공시가격 추정, 납부 일정."""
from datetime import date

import pytest

from engine.calculator import calculate_total
from engine.estimator import estimate_official_price
from engine.models import House, TaxpayerInput
from engine.utils import parse_korean_amount


@pytest.mark.parametrize("text, expected", [
    ("10억", 1_000_000_000),
    ("7억 5천", 750_000_000),
    ("7억 5천만", 750_000_000),
    ("15억5000만원", 1_550_000_000),
    ("15억5000", 1_550_000_000),
    ("15억 5,000만 원", 1_550_000_000),
    ("3,500만", 35_000_000),
    ("3천5백만", 35_000_000),
    ("850,000,000", 850_000_000),
    ("850000000원", 850_000_000),
    ("4.8억", 480_000_000),
    ("약 123만 원", 1_230_000),
    ("1조 2000억", 1_200_000_000_000),
    ("억", 100_000_000),
    (1_000_000, 1_000_000),
])
def test_parse_korean_amount(text, expected):
    assert parse_korean_amount(text) == expected


@pytest.mark.parametrize("bad", ["", "abc", "10억abc", "-5억", -1])
def test_parse_korean_amount_invalid(bad):
    with pytest.raises(ValueError):
        parse_korean_amount(bad)


def test_estimate_official_price():
    est = estimate_official_price(1_000_000_000)
    assert est["realization_rate"] == 0.69
    assert est["estimated_official_price"] == 690_000_000


def test_market_price_only_is_estimated_and_flagged():
    """TC-11: 실거래가 15억 → 추정 공시가격 10.35억."""
    inp = TaxpayerInput(birth_date=date(1976, 1, 1), houses=[
        House(name="A", market_price=1_500_000_000, acquired_date=date(2020, 1, 1))])
    r = calculate_total(inp)
    h = r.property_tax_by_house[0]
    assert h.official_price == 1_035_000_000
    assert h.price_estimated
    assert any("추정" in w for w in r.warnings)
    assert r.steps[0].label == "[A] 공시가격 추정"


def test_payment_schedule_installment(make_input):
    """3주택 15억×3: 종부세가 500만 원 초과 → 50% 분납 안내."""
    r = calculate_total(make_input([1_500_000_000] * 3))
    dec = r.payment_schedule[2]
    assert dec["month"] == 12
    assert dec["installment_available"] > 0
    assert "2027.6.15" in dec["installment_note"]
    assert [p["period"] for p in r.payment_schedule][0] == "2026.7.16 ~ 7.31"
