"""재산세 단위테스트. 기댓값은 PRD 6.2 세율표로 손계산한 값."""
from datetime import date

import pytest
from pydantic import ValidationError

from engine.models import House, TaxpayerInput
from engine.property_tax import calculate_property_tax
from engine.rules_loader import load_rules
from engine.utils import progressive_tax

STD = load_rules(2026)["property_tax"]["standard_rates"]["brackets"]
SPECIAL = load_rules(2026)["property_tax"]["one_house_special_rates"]["brackets"]


@pytest.mark.parametrize("base, expected", [
    (60_000_000, 60_000),          # 6천만 × 0.1%
    (60_000_001, 60_000),          # 초과 1원 × 0.15% → 0.0015원
    (150_000_000, 195_000),        # 6만 + 9천만 × 0.15%
    (300_000_000, 570_000),        # 19.5만 + 1.5억 × 0.25%
    (300_001_000, 570_004),        # 57만 + 1천 원 × 0.4%
])
def test_standard_rate_boundaries(base, expected):
    assert int(progressive_tax(base, STD)) == expected


@pytest.mark.parametrize("base, expected", [
    (60_000_000, 30_000), (150_000_000, 120_000), (300_000_000, 420_000),
])
def test_special_rate_boundaries(base, expected):
    assert int(progressive_tax(base, SPECIAL)) == expected


def test_multi_house_general(make_input):
    """2주택 중 공시가 5억: 과표 5억×60%=3억 → 본세 57만, 도시지역분 42만, 지방교육세 11.4만."""
    r = calculate_property_tax(make_input([500_000_000, 300_000_000]))
    h = r.houses[0]
    assert (h.tax_base, h.property_tax, h.urban_area_tax, h.local_education_tax) == (
        300_000_000, 570_000, 420_000, 114_000)
    assert not h.special_rate_applied


def test_one_house_special_ratio_and_rate(make_input):
    """1주택 공시가 5억: 비율 44% → 과표 2.2억 → 특례세율 12만 + 7천만×0.2% = 26만."""
    h = calculate_property_tax(make_input([500_000_000])).houses[0]
    assert h.fair_market_ratio == 0.44
    assert h.tax_base == 220_000_000
    assert h.special_rate_applied
    assert h.property_tax == 260_000
    assert h.urban_area_tax == 308_000
    assert h.local_education_tax == 52_000


@pytest.mark.parametrize("price, ratio", [
    (300_000_000, 0.43), (300_000_001, 0.44), (600_000_000, 0.44), (600_000_001, 0.45),
])
def test_one_house_ratio_boundaries(make_input, price, ratio):
    assert calculate_property_tax(make_input([price])).houses[0].fair_market_ratio == ratio


def test_special_rate_9eok_boundary(make_input):
    """9억: 과표 4.05억 특례세율 787,500원 / 9억+1원: 표준세율 990,000원."""
    at = calculate_property_tax(make_input([900_000_000])).houses[0]
    over = calculate_property_tax(make_input([900_000_001])).houses[0]
    assert at.special_rate_applied and at.property_tax == 787_500
    assert not over.special_rate_applied and over.property_tax == 990_000


def test_non_urban_area_has_no_urban_tax(make_input):
    h = calculate_property_tax(make_input([500_000_000], is_urban_area=False)).houses[0]
    assert h.urban_area_tax == 0


def test_ownership_share(make_input):
    """공동명의 50%: 1주택 5억 본세 26만 → 13만."""
    h = calculate_property_tax(make_input([500_000_000], ownership_ratio=0.5)).houses[0]
    assert h.property_tax == 130_000
    assert h.urban_area_tax == 154_000


def test_lump_sum_july_when_small(make_input):
    h = calculate_property_tax(make_input([200_000_000])).houses[0]
    assert h.property_tax <= 200_000
    assert (h.july, h.september) == (h.total, 0)


def test_split_payment_when_large(make_input):
    h = calculate_property_tax(make_input([500_000_000, 300_000_000])).houses[0]
    assert h.july + h.september == h.total
    assert h.september > 0


def test_excluded_house_not_counted_for_one_house(make_input):
    """상속주택 등 특례 체크 주택은 주택 수에서 빠져 나머지 1채가 1주택 특례를 받는다."""
    inp = TaxpayerInput(birth_date=date(1976, 1, 1), houses=[
        House(name="본채", official_price=500_000_000, acquired_date=date(2020, 1, 1)),
        House(name="상속", official_price=100_000_000, acquired_date=date(2024, 1, 1), exclude_from_count=True),
    ])
    r = calculate_property_tax(inp)
    assert r.houses[0].fair_market_ratio == 0.44
    assert r.houses[1].fair_market_ratio == 0.60


def test_base_cap_not_applied_when_rate_missing(make_input):
    inp = make_input([500_000_000], prev_property_tax_base={"H1": 100_000_000})
    r = calculate_property_tax(inp)
    assert r.houses[0].tax_base == 220_000_000
    assert any("과표상한률" in w for w in r.warnings)


def test_base_cap_applied_when_rate_set(make_input):
    rules = load_rules(2026)
    rules = {**rules, "property_tax": {**rules["property_tax"], "base_cap_rate": 0.05}}
    inp = make_input([500_000_000], prev_property_tax_base={"H1": 200_000_000})
    assert calculate_property_tax(inp, rules).houses[0].tax_base == 210_000_000


@pytest.mark.parametrize("bad", [
    dict(official_price=0), dict(official_price=-1), dict(ownership_ratio=0), dict(ownership_ratio=1.5),
    dict(acquired_date=date(2026, 6, 2)), dict(official_price=None),
])
def test_input_validation(bad):
    kw = dict(name="X", official_price=500_000_000, acquired_date=date(2020, 1, 1)) | bad
    with pytest.raises(ValidationError):
        House(**kw)


def test_market_price_only_requires_estimation_stage(make_input):
    inp = TaxpayerInput(birth_date=date(1976, 1, 1), houses=[
        House(name="X", market_price=1_000_000_000, acquired_date=date(2020, 1, 1))])
    with pytest.raises(ValueError, match="공시가격"):
        calculate_property_tax(inp)
