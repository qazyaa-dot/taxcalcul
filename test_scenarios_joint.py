"""What-if 시나리오와 공동명의 비교."""
from datetime import date

import pytest

from engine.calculator import calculate_total
from engine.joint import compare_joint_ownership
from engine.models import House
from engine.scenarios import Scenario, apply_scenario, compare_scenarios


def test_sell_one_of_two(make_input):
    """2주택 10억+7억 중 7억 매도 → 1주택 10억: 종부세 0원, 재산세는 1주택 특례비율."""
    inp = make_input([1_000_000_000, 700_000_000])
    out = compare_scenarios(inp, [Scenario(kind="sell", house_name="H2")])
    row = out["scenarios"][0]
    expected = calculate_total(make_input([1_000_000_000]))
    assert row["total"] == expected.total
    assert row["comprehensive"] == 0
    assert row["diff_total"] == row["total"] - out["base"]["total"] < 0
    assert row["label"] == "H2 매도"


def test_sell_last_house_gives_zero(make_input):
    out = compare_scenarios(make_input([500_000_000]), [Scenario(kind="sell", house_name="H1")])
    assert out["scenarios"][0]["total"] == 0


def test_years_later_increases_credits(make_input):
    """1주택 20억, 만 59세·보유 4년 → 5년 후 만 64세(20%)·보유 9년(20%)."""
    inp = make_input([2_000_000_000], birth=date(1967, 1, 1), acquired=date(2022, 1, 1))
    later = apply_scenario(inp, Scenario(kind="years_later", years=5))
    assert later.birth_date == date(1962, 1, 1)
    assert later.houses[0].acquired_date == date(2017, 1, 1)
    out = compare_scenarios(inp, [Scenario(kind="years_later", years=5)])
    assert out["scenarios"][0]["diff_comprehensive"] < 0


def test_price_change(make_input):
    inp = make_input([1_000_000_000, 500_000_000])
    one = apply_scenario(inp, Scenario(kind="price_change", percent=10, house_name="H1"))
    assert [h.official_price for h in one.houses] == [1_100_000_000, 500_000_000]
    every = apply_scenario(inp, Scenario(kind="price_change", percent=-20))
    assert [h.official_price for h in every.houses] == [800_000_000, 400_000_000]


def test_add_house_makes_multi(make_input):
    inp = make_input([1_000_000_000])
    new = House(name="추가", official_price=500_000_000, acquired_date=date(2025, 1, 1))
    out = compare_scenarios(inp, [Scenario(kind="add_house", house=new)])
    assert out["scenarios"][0]["result"].property_tax_by_house[0].fair_market_ratio == 0.60


@pytest.mark.parametrize("sc", [
    Scenario(kind="sell", house_name="없는집"),
    Scenario(kind="hold_years"),
    Scenario(kind="price_change"),
    Scenario(kind="add_house"),
])
def test_invalid_scenarios(make_input, sc):
    with pytest.raises(ValueError):
        apply_scenario(make_input([500_000_000]), sc)


def test_joint_ownership_comparison(make_input):
    """공동명의 50:50 20억, 본인 만 60세·보유 10년, 배우자 만 58세.

    A(각자): 지분 10억 − 9억 = 1억 × 60% = 6천만 → 산출 30만
        재산세 본인 지분 = 297만 × 50% = 148.5만, 중복분 = 148.5만 × (6천만×60%×0.4%) / 177만 = 120,810
        → 179,190 + 농특세 35,830 = 215,020 (10원 미만 절사) → 부부 합계 430,040
    B(특례): 산출 276만 − 중복분 86.4만 = 189.6만 × (1 − 60%) = 758,400 + 농특세 151,680 = 910,080
    """
    inp = make_input([2_000_000_000], birth=date(1966, 1, 1), acquired=date(2016, 1, 1), ownership_ratio=0.5)
    out = compare_joint_ownership(inp, spouse_birth_date=date(1968, 1, 1))
    assert out["option_a"]["me"]["comprehensive"] == 215_020
    assert out["option_a"]["comprehensive"] == 430_040
    assert out["option_b"]["comprehensive"] == 910_080
    assert out["option_b"]["payer"] == "본인"
    assert out["better"] == "A"
    assert out["saving"] == 910_080 - 430_040


def test_joint_requires_partial_single_house(make_input):
    with pytest.raises(ValueError):
        compare_joint_ownership(make_input([1_000_000_000]), date(1970, 1, 1))
