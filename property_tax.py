"""주택분 재산세 계산 (주택별 과세, PRD 6.2)."""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from .household import is_one_house_target
from .models import CalculationStep, House, HousePropertyTax, PropertyTaxResult, TaxpayerInput
from .rules_loader import load_rules
from .utils import D, pct, progressive_tax, truncate, won


def require_official_price(h: House) -> int:
    if h.official_price is None:
        raise ValueError(f"'{h.name}'의 공시가격이 없습니다. (실거래가 기반 추정은 2단계에서 지원)")
    return h.official_price


def fair_market_ratio(price: int, one_house: bool, pt_rules: dict[str, Any]) -> Decimal:
    """공정시장가액비율: 1세대1주택은 공시가격 구간별 특례, 그 외 일반 비율."""
    fmr = pt_rules["fair_market_ratio"]
    if not one_house:
        return D(fmr["general"])
    for b in fmr["one_house"]["brackets"]:
        if b["max_price"] is None or price <= b["max_price"]:
            return D(b["ratio"])
    raise AssertionError("unreachable")


def property_tax_rate_table(price: int, one_house: bool, pt_rules: dict[str, Any]) -> tuple[list, bool]:
    """적용 세율표와 특례세율 적용 여부 (1세대1주택 + 공시가격 9억 이하면 특례)."""
    special = pt_rules["one_house_special_rates"]
    if one_house and price <= special["price_limit"]:
        return special["brackets"], True
    return pt_rules["standard_rates"]["brackets"], False


def calculate_property_tax(inp: TaxpayerInput, rules: dict[str, Any] | None = None) -> PropertyTaxResult:
    """주택별 재산세·도시지역분·지방교육세를 계산하고 지분율만큼 안분한다."""
    rules = rules or load_rules(inp.tax_year)
    pt = rules["property_tax"]
    base_unit, tax_unit = rules["rounding"]["base_unit"], rules["rounding"]["tax_unit"]
    steps: list[CalculationStep] = []
    warnings: list[str] = []
    results: list[HousePropertyTax] = []

    for h in inp.houses:
        price = require_official_price(h)
        one_house = is_one_house_target(inp, h)
        tag = f"[{h.name}] "
        share = D(h.ownership_ratio)

        ratio = fair_market_ratio(price, one_house, pt)
        base = truncate(D(price) * ratio, base_unit)
        ratio_basis = "지방세법 시행령 §109 (1세대1주택 특례)" if one_house else "지방세법 시행령 §109"
        steps.append(CalculationStep(
            tax="재산세", label=tag + "과세표준",
            formula=f"공시가격 {won(price)} × 공정시장가액비율 {pct(ratio)}",
            value=base, basis=ratio_basis))

        prev_base = (inp.prev_property_tax_base or {}).get(h.name)
        if prev_base is not None:
            cap_rate = pt["base_cap_rate"]
            if cap_rate is None:
                warnings.append(f"{h.name}: 과표상한률이 규칙 파일에 설정되지 않아 과세표준상한제를 적용하지 않았습니다")
            else:
                cap = truncate(D(prev_base) * (1 + D(cap_rate)), base_unit)
                if cap < base:
                    steps.append(CalculationStep(
                        tax="재산세", label=tag + "과세표준상한 적용",
                        formula=f"min({won(base)}, 전년도 과표 {won(prev_base)} × (1 + {pct(cap_rate)}))",
                        value=cap, basis="지방세법 §110③"))
                    base = cap

        table, special = property_tax_rate_table(price, one_house, pt)
        tax_full = progressive_tax(base, table)
        prop_tax = truncate(tax_full * share, tax_unit)
        rate_name = "1세대1주택 특례세율" if special else "표준세율"
        share_txt = f" × 지분 {pct(share)}" if share != 1 else ""
        steps.append(CalculationStep(
            tax="재산세", label=tag + "재산세 본세",
            formula=f"과세표준 {won(base)}에 {rate_name} 누진 적용 = {won(truncate(tax_full, 1))}{share_txt}",
            value=prop_tax, basis="지방세법 §111의2" if special else "지방세법 §111①3"))

        urban = truncate(D(base) * D(pt["urban_area_rate"]) * share, tax_unit) if h.is_urban_area else 0
        steps.append(CalculationStep(
            tax="부가세", label=tag + "도시지역분",
            formula=(f"과세표준 {won(base)} × {pct(pt['urban_area_rate'])}{share_txt}"
                     if h.is_urban_area else "도시지역 외 주택 → 비과세"),
            value=urban, basis="지방세법 §112"))

        edu = truncate(D(prop_tax) * D(pt["local_education_rate"]), tax_unit)
        steps.append(CalculationStep(
            tax="부가세", label=tag + "지방교육세",
            formula=f"재산세 본세 {won(prop_tax)} × {pct(pt['local_education_rate'])}",
            value=edu, basis="지방세법 §151"))

        total = prop_tax + urban + edu
        if prop_tax <= pt["lump_sum_threshold"]:
            july, september = total, 0
        else:
            july = truncate(D(total) / 2, tax_unit)
            september = total - july

        results.append(HousePropertyTax(
            name=h.name, official_price=price, ownership_ratio=h.ownership_ratio,
            fair_market_ratio=float(ratio), tax_base=base, special_rate_applied=special,
            price_estimated=h.price_estimated,
            property_tax=prop_tax, urban_area_tax=urban, local_education_tax=edu,
            total=total, july=july, september=september))

    return PropertyTaxResult(
        houses=results,
        property_tax_total=sum(r.property_tax for r in results),
        urban_area_tax=sum(r.urban_area_tax for r in results),
        local_education_tax=sum(r.local_education_tax for r in results),
        total=sum(r.total for r in results),
        steps=steps, warnings=warnings)
