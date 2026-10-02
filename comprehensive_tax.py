"""주택분 종합부동산세 계산 (인별 합산 과세, PRD 6.3)."""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from .household import (
    age_on_assessment, counted_houses, holding_years, house_count,
    is_one_house_owner_for_comprehensive,
)
from .models import CalculationStep, ComprehensiveTaxResult, PropertyTaxResult, TaxpayerInput
from .property_tax import require_official_price
from .rules_loader import load_rules
from .utils import D, pct, progressive_tax, truncate, won


def credit_rate(value: int, brackets: list) -> Decimal:
    """[최소값, 공제율] 구간표에서 해당 공제율 (미달이면 0)."""
    rate = Decimal(0)
    for minimum, r in brackets:
        if value >= minimum:
            rate = D(r)
    return rate


def installment_amount(tax: int, inst: dict[str, int], tax_unit: int) -> int:
    """분할납부 가능 금액."""
    if tax <= inst["threshold"]:
        return 0
    if tax <= inst["half_threshold"]:
        return tax - inst["threshold"]
    return truncate(D(tax) / 2, tax_unit)


def calculate_comprehensive_tax(
    inp: TaxpayerInput, prop: PropertyTaxResult, rules: dict[str, Any] | None = None,
) -> ComprehensiveTaxResult:
    """재산세 결과를 받아 종부세·농어촌특별세를 계산한다."""
    rules = rules or load_rules(inp.tax_year)
    ct, pt = rules["comprehensive_tax"], rules["property_tax"]
    base_unit, tax_unit = rules["rounding"]["base_unit"], rules["rounding"]["tax_unit"]
    steps: list[CalculationStep] = []
    warnings: list[str] = []

    one_owner = is_one_house_owner_for_comprehensive(inp)
    count = house_count(inp.houses)
    price_sum = sum(int(D(require_official_price(h)) * D(h.ownership_ratio)) for h in inp.houses)
    steps.append(CalculationStep(
        tax="종부세", label="공시가격 합계(인별, 지분 반영)",
        formula=" + ".join(f"{h.name} {won(h.official_price)}" + (f"×{pct(h.ownership_ratio)}" if h.ownership_ratio != 1 else "")
                           for h in inp.houses),
        value=price_sum, basis="종부세법 §7"))

    deduction = ct["deduction"]["one_house" if one_owner else "general"]
    fmr = D(ct["fair_market_ratio"])
    base = truncate(max(D(0), D(price_sum - deduction)) * fmr, base_unit)
    steps.append(CalculationStep(
        tax="종부세", label="과세표준",
        formula=(f"({won(price_sum)} − 기본공제 {won(deduction)}"
                 f"{' [1세대1주택자]' if one_owner else ''}) × 공정시장가액비율 {pct(fmr)}"),
        value=base, basis="종부세법 §8①"))

    empty = dict(
        is_one_house_owner=one_owner, house_count=count, price_sum=price_sum, deduction=deduction,
        senior_credit_rate=0.0, long_term_credit_rate=0.0,
    )
    if base == 0:
        steps.append(CalculationStep(tax="종부세", label="종부세", formula="과세표준 0원 → 과세 대상 아님", value=0))
        return ComprehensiveTaxResult(
            taxable=False, tax_base=0, calculated_tax=0, property_tax_overlap=0, credit_amount=0,
            burden_cap_reduction=0, comprehensive_tax=0, rural_special_tax=0, total=0,
            installment_available=0, steps=steps, warnings=warnings, **empty)

    heavy = count >= ct["heavy_house_count"]
    table = ct["rates_3plus" if heavy else "rates_upto_2"]["brackets"]
    calculated = truncate(progressive_tax(base, table), tax_unit)
    steps.append(CalculationStep(
        tax="종부세", label="산출세액",
        formula=f"과세표준 {won(base)}에 {'3주택 이상' if heavy else '2주택 이하'} 세율 누진 적용 (주택 수 {count}채)",
        value=calculated, basis="종부세법 §9①"))

    # 재산세 중복분 공제 (시행령 §4의3)
    counted = counted_houses(inp.houses)
    if one_owner:
        prop_ratio = D(next(r.fair_market_ratio for r in prop.houses if r.name == counted[0].name))
    else:
        prop_ratio = D(pt["fair_market_ratio"]["general"])
    numerator = D(base) * prop_ratio * D(ct["property_tax_overlap"]["numerator_rate"])
    denominator = progressive_tax(D(price_sum) * prop_ratio, pt["standard_rates"]["brackets"])
    paid = prop.property_tax_total
    overlap = truncate(D(paid) * numerator / denominator, tax_unit) if denominator > 0 else 0
    overlap = min(overlap, paid, calculated)
    steps.append(CalculationStep(
        tax="종부세", label="재산세 중복분 공제",
        formula=(f"재산세 본세 {won(paid)} × [과세표준 {won(base)} × {pct(prop_ratio)} × "
                 f"{pct(ct['property_tax_overlap']['numerator_rate'])}] ÷ [공시가격 합계 {won(price_sum)} × "
                 f"{pct(prop_ratio)}에 재산세 표준세율 적용 {won(truncate(denominator, 1))}]"),
        value=overlap, basis="종부세법 시행령 §4의3 (★산식 확인 필요)"))
    after_overlap = calculated - overlap

    senior = long_term = Decimal(0)
    credit = 0
    if one_owner:
        age = age_on_assessment(inp.birth_date)
        years = holding_years(counted[0].acquired_date)
        senior = credit_rate(age, ct["senior_credit"]["brackets"])
        long_term = credit_rate(years, ct["long_term_credit"]["brackets"])
        total_rate = min(senior + long_term, D(ct["credit_cap"]))
        credit = truncate(D(after_overlap) * total_rate, tax_unit)
        cap_txt = f" → 한도 {pct(ct['credit_cap'])}" if senior + long_term > D(ct["credit_cap"]) else ""
        steps.append(CalculationStep(
            tax="종부세", label="1세대1주택자 세액공제",
            formula=(f"{won(after_overlap)} × (고령자 만 {age}세 {pct(senior)} + "
                     f"장기보유 {years}년 {pct(long_term)}{cap_txt})"),
            value=credit, basis="종부세법 §9⑤~⑧"))
    after_credit = after_overlap - credit

    reduction = 0
    if inp.prev_property_tax is None or inp.prev_comprehensive_tax is None:
        warnings.append("세부담상한 미반영: 전년도 재산세·종부세가 입력되지 않았습니다")
    else:
        current_prop = prop.property_tax_total + prop.urban_area_tax
        limit = truncate(
            D(inp.prev_property_tax + inp.prev_comprehensive_tax) * D(ct["burden_cap_rate"]) - current_prop,
            tax_unit)
        reduction = max(0, after_credit - limit)
        steps.append(CalculationStep(
            tax="종부세", label="세부담상한 초과세액",
            formula=(f"상한 = (전년도 {won(inp.prev_property_tax)} + {won(inp.prev_comprehensive_tax)}) × "
                     f"{pct(ct['burden_cap_rate'])} − 당해 재산세 {won(current_prop)} = {won(limit)}"),
            value=reduction, basis="종부세법 §10 (★재산세 범위 확인 필요)"))
    comp_tax = after_credit - reduction
    steps.append(CalculationStep(tax="종부세", label="종부세 결정세액",
                                 formula=f"{won(calculated)} − {won(overlap)} − {won(credit)} − {won(reduction)}",
                                 value=comp_tax, basis="종부세법 §9·§10"))

    rural = truncate(D(comp_tax) * D(ct["rural_special_rate"]), tax_unit)
    steps.append(CalculationStep(tax="부가세", label="농어촌특별세",
                                 formula=f"종부세 {won(comp_tax)} × {pct(ct['rural_special_rate'])}",
                                 value=rural, basis="농어촌특별세법 §5①"))

    return ComprehensiveTaxResult(
        taxable=True, is_one_house_owner=one_owner, house_count=count, price_sum=price_sum,
        deduction=deduction, tax_base=base, calculated_tax=calculated, property_tax_overlap=overlap,
        senior_credit_rate=float(senior), long_term_credit_rate=float(long_term), credit_amount=credit,
        burden_cap_reduction=reduction, comprehensive_tax=comp_tax, rural_special_tax=rural,
        total=comp_tax + rural, installment_available=installment_amount(comp_tax, ct["installment"], tax_unit),
        steps=steps, warnings=warnings)
