"""원스톱 계산: 재산세 → 종부세 → 합계·납부일정 (PRD 6.4)."""
from __future__ import annotations

from typing import Any

from .comprehensive_tax import calculate_comprehensive_tax
from .estimator import fill_missing_prices
from .household import (
    age_on_assessment, exclusion_ignored, house_count, is_one_house_household,
    is_one_house_owner_for_comprehensive, one_house_override_conflict,
)
from .models import CalculationStep, TaxpayerInput, TaxResult
from .property_tax import calculate_property_tax
from .rules_loader import load_rules
from .utils import won


def calculate_total(inp: TaxpayerInput, rules: dict[str, Any] | None = None) -> TaxResult:
    """보유세 전체를 계산해 TaxResult로 반환한다."""
    rules = rules or load_rules(inp.tax_year)
    inp, est_steps, est_warnings = fill_missing_prices(inp, rules)

    prelim = est_steps + [
        CalculationStep(tax="공통", label="보유 주택 수(산정 대상)", formula=f"입력 {len(inp.houses)}채 중 특례 제외 후",
                        value=house_count(inp.houses), basis="종부세법 시행령 §4의2", unit="채"),
        CalculationStep(tax="공통", label="과세기준일 만 나이", formula=f"생년월일 {inp.birth_date} 기준 2026-06-01",
                        value=age_on_assessment(inp.birth_date), unit="세"),
    ]
    input_warnings = []
    if one_house_override_conflict(inp):
        input_warnings.append(
            f"1세대1주택 '예'를 선택했지만 산정 대상 주택이 {house_count(inp.houses)}채라 특례를 적용하지 않았습니다")
    if exclusion_ignored(inp.houses) and len(inp.houses) == 1:
        input_warnings.append("주택 수 제외 특례는 다른 주택이 있을 때만 적용되므로 이 주택을 1채로 보고 계산했습니다")
    elif exclusion_ignored(inp.houses):
        input_warnings.append("모든 주택에 주택 수 제외 특례가 체크되어 특례를 적용하지 않고 주택 수를 셌습니다")
    one_hh = is_one_house_household(inp)
    one_owner = is_one_house_owner_for_comprehensive(inp)
    prelim.append(CalculationStep(
        tax="공통", label="1세대1주택 판정",
        formula=(f"재산세 특례 {'적용' if one_hh else '미적용'} / "
                 f"종부세 1세대1주택자 {'해당' if one_owner else '비해당'}"
                 + (" (공동명의는 종부세 1세대1주택자 아님)" if one_hh and not one_owner else "")),
        value=int(one_hh), basis="지방세법 §111의2, 종부세법 §2", unit="여부"))

    prop = calculate_property_tax(inp, rules)
    comp = calculate_comprehensive_tax(inp, prop, rules)

    total = prop.total + comp.total
    price_sum = comp.price_sum
    july = sum(h.july for h in prop.houses)
    september = sum(h.september for h in prop.houses)
    year = inp.tax_year
    schedule = [
        {"month": 7, "label": "재산세 1기분 (주택분 1/2, 20만 원 이하는 일괄)", "period": f"{year}.7.16 ~ 7.31",
         "amount": july},
        {"month": 9, "label": "재산세 2기분 (주택분 1/2)", "period": f"{year}.9.16 ~ 9.30", "amount": september},
        {"month": 12, "label": "종합부동산세 + 농어촌특별세", "period": f"{year}.12.1 ~ 12.15", "amount": comp.total,
         "installment_available": comp.installment_available,
         "installment_note": (f"종부세 {won(comp.installment_available)}은 {year + 1}.6.15까지 분할납부 가능"
                              if comp.installment_available else "")},
    ]
    summary = CalculationStep(
        tax="공통", label="총 보유세",
        formula=f"재산세 계 {won(prop.total)} + 종부세 계 {won(comp.total)}", value=total)

    return TaxResult(
        property_tax_by_house=prop.houses,
        property_tax_total=prop.property_tax_total,
        urban_area_tax=prop.urban_area_tax,
        local_education_tax=prop.local_education_tax,
        comprehensive_tax=comp.comprehensive_tax,
        rural_special_tax=comp.rural_special_tax,
        total=total,
        effective_rate=round(total / price_sum, 6) if price_sum else 0.0,
        payment_schedule=schedule,
        steps=prelim + prop.steps + comp.steps + [summary],
        warnings=input_warnings + est_warnings + prop.warnings + comp.warnings,
    )
