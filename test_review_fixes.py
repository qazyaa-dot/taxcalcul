"""4단계 검토(REVIEW_REPORT.md) 버그 수정 회귀 테스트 — 엔진."""
from datetime import date

from engine.calculator import calculate_total
from engine.models import House, TaxpayerInput


def test_b01_one_house_override_with_two_houses_is_ignored(make_input):
    """B-01: '1세대1주택 예' + 2채 → 특례 미적용(60%) + 경고. 자동 판정과 같은 세액."""
    forced = calculate_total(make_input([900_000_000, 500_000_000], is_one_house_household=True))
    auto = calculate_total(make_input([900_000_000, 500_000_000]))
    assert [h.fair_market_ratio for h in forced.property_tax_by_house] == [0.60, 0.60]
    assert forced.total == auto.total
    assert any("1세대1주택 '예'" in w for w in forced.warnings)


def test_b01_override_yes_with_one_house_still_allowed(make_input):
    r = calculate_total(make_input([900_000_000], is_one_house_household=True))
    assert r.property_tax_by_house[0].fair_market_ratio == 0.45
    assert not any("1세대1주택 '예'" in w for w in r.warnings)


def test_b06_single_excluded_house_counts_as_one_house():
    """B-06: 제외 특례만 체크한 1채 → 1주택으로 보고 특례(44%) 적용 + 안내."""
    inp = TaxpayerInput(birth_date=date(1970, 1, 1), houses=[
        House(name="상속", official_price=500_000_000, acquired_date=date(2024, 1, 1), exclude_from_count=True)])
    r = calculate_total(inp)
    assert r.property_tax_by_house[0].fair_market_ratio == 0.44
    assert r.property_tax_by_house[0].special_rate_applied
    assert any("다른 주택이 있을 때만" in w for w in r.warnings)


def test_b06_exclusion_still_works_with_other_house():
    inp = TaxpayerInput(birth_date=date(1970, 1, 1), houses=[
        House(name="본채", official_price=500_000_000, acquired_date=date(2020, 1, 1)),
        House(name="상속", official_price=100_000_000, acquired_date=date(2024, 1, 1), exclude_from_count=True)])
    r = calculate_total(inp)
    assert [h.fair_market_ratio for h in r.property_tax_by_house] == [0.44, 0.60]
    assert not any("제외 특례" in w for w in r.warnings)


def test_b07_non_money_steps_have_units(make_input):
    r = calculate_total(make_input([2_000_000_000], birth=date(1960, 3, 1)))
    by_label = {s.label: s for s in r.steps}
    assert by_label["보유 주택 수(산정 대상)"].display_value() == "1채"
    assert by_label["과세기준일 만 나이"].display_value() == "66세"
    assert by_label["1세대1주택 판정"].display_value() == "예"
    assert by_label["총 보유세"].display_value() == f"{r.total:,}원"
