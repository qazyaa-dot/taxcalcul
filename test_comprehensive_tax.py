"""종부세 단위테스트. 기댓값은 PRD 6.3 세율표로 손계산한 값."""
from datetime import date

import pytest

from engine.calculator import calculate_total
from engine.comprehensive_tax import calculate_comprehensive_tax
from engine.household import age_on_assessment, holding_years
from engine.property_tax import calculate_property_tax
from engine.rules_loader import load_rules
from engine.utils import progressive_tax

CT = load_rules(2026)["comprehensive_tax"]


def comp(inp):
    return calculate_comprehensive_tax(inp, calculate_property_tax(inp))


def test_one_house_20eok_senior_long_term(make_input):
    """1주택 20억, 만 66세, 12년 보유.
    과표 (20억−12억)×60%=4.8억 → 산출 150만+1.8억×0.7%=276만
    재산세 본세 297만(과표 9억 표준세율), 중복분 = 297만 × (4.8억×45%×0.4%) / 297만 = 86.4만
    공제 후 189.6만 × (30%+40%) = 132.72만 → 결정 56.88만, 농특세 11.376만
    """
    r = comp(make_input([2_000_000_000], birth=date(1960, 3, 1), acquired=date(2014, 1, 1)))
    assert r.is_one_house_owner
    assert r.tax_base == 480_000_000
    assert r.calculated_tax == 2_760_000
    assert r.property_tax_overlap == 864_000
    assert r.credit_amount == 1_327_200
    assert r.comprehensive_tax == 568_800
    assert r.rural_special_tax == 113_760


@pytest.mark.parametrize("price, taxable", [(1_200_000_000, False), (1_210_000_000, True)])
def test_one_house_12eok_deduction_boundary(make_input, price, taxable):
    assert comp(make_input([price])).taxable is taxable


def test_multi_house_9eok_deduction(make_input):
    """2주택 10억+7억: (17억−9억)×60%=4.8억 → 산출 276만, 세액공제 없음."""
    r = comp(make_input([1_000_000_000, 700_000_000], birth=date(1950, 1, 1), acquired=date(2000, 1, 1)))
    assert not r.is_one_house_owner
    assert r.deduction == 900_000_000
    assert r.tax_base == 480_000_000
    assert r.calculated_tax == 2_760_000
    assert r.credit_amount == 0


def test_credit_cap_80(make_input):
    """만 72세(40%) + 16년(50%) = 90% → 한도 80%."""
    r = comp(make_input([3_000_000_000], birth=date(1954, 1, 1), acquired=date(2010, 1, 1)))
    assert r.senior_credit_rate == 0.4 and r.long_term_credit_rate == 0.5
    after_overlap = r.calculated_tax - r.property_tax_overlap
    assert r.credit_amount == after_overlap * 8 // 10 // 10 * 10


def test_heavy_rate_for_3_houses(make_input):
    """3주택 15억×3: (45억−9억)×60%=21.6억 → 150만+210만+600만+9.6억×2%=2,880만."""
    r = comp(make_input([1_500_000_000] * 3))
    assert r.house_count == 3
    assert r.tax_base == 2_160_000_000
    assert r.calculated_tax == 28_800_000


def test_two_house_rate_same_base(make_input):
    """같은 과표 21.6억을 2주택 세율로: 9.6억×1.3% → 2,208만."""
    assert int(progressive_tax(2_160_000_000, CT["rates_upto_2"]["brackets"])) == 22_080_000


def test_joint_ownership_not_one_house_owner(make_input):
    """공동명의 50%: 종부세 1세대1주택자 아님 → 9억 공제, 20억×50%=10억 → 과표 6천만."""
    r = comp(make_input([2_000_000_000], ownership_ratio=0.5))
    assert not r.is_one_house_owner
    assert r.price_sum == 1_000_000_000
    assert r.tax_base == 60_000_000


def test_burden_cap(make_input):
    """2주택 15억×2, 전년도 합계 900만 → 상한 1,350만 − 당해 재산세(본세+도시지역분)."""
    inp = make_input([1_500_000_000, 1_500_000_000], prev_property_tax=6_000_000, prev_comprehensive_tax=3_000_000)
    r = comp(inp)
    prop = calculate_property_tax(inp)
    limit = 9_000_000 * 3 // 2 - (prop.property_tax_total + prop.urban_area_tax)
    assert r.burden_cap_reduction > 0
    assert r.comprehensive_tax == limit


def test_burden_cap_warning_when_prev_missing(make_input):
    assert any("세부담상한" in w for w in comp(make_input([2_000_000_000])).warnings)


def test_installment(make_input):
    r = comp(make_input([1_500_000_000] * 3))
    assert r.installment_available == r.comprehensive_tax // 2 // 10 * 10


@pytest.mark.parametrize("birth, expected", [
    (date(1966, 6, 1), 60), (date(1966, 6, 2), 59), (date(1961, 6, 1), 65), (date(1956, 6, 2), 69),
])
def test_age_boundary(birth, expected):
    assert age_on_assessment(birth) == expected


@pytest.mark.parametrize("acq, years", [(date(2021, 6, 1), 5), (date(2021, 6, 2), 4), (date(2011, 6, 1), 15)])
def test_holding_years_boundary(acq, years):
    assert holding_years(acq) == years


def test_total_and_steps(make_input):
    r = calculate_total(make_input([2_000_000_000], birth=date(1960, 3, 1), acquired=date(2014, 1, 1)))
    assert r.total == 5_506_560
    assert sum(p["amount"] for p in r.payment_schedule) == r.total
    labels = [s.label for s in r.steps]
    assert "재산세 중복분 공제" in labels and "농어촌특별세" in labels
