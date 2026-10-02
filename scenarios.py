"""What-if 시나리오 비교 (FR-AI-04, FR-OUT-05). 현행(2026년 귀속) 세법을 그대로 적용한다."""
from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field

from .calculator import calculate_total
from .models import House, TaxpayerInput, TaxResult
from .rules_loader import load_rules
from .utils import D, truncate

ScenarioKind = Literal["sell", "hold_years", "age", "years_later", "price_change", "add_house"]


class Scenario(BaseModel):
    """변경안 하나.

    - sell: house_name 주택 매도(제외)
    - hold_years: 보유기간 +years년 / age: 나이 +years세 / years_later: 보유기간·나이 모두 +years
    - price_change: 공시가격 percent% 변동 (house_name 없으면 전체)
    - add_house: house 추가
    """

    kind: ScenarioKind
    house_name: str | None = None
    years: int | None = Field(default=None, ge=1, le=50)
    percent: float | None = Field(default=None, gt=-100, le=500)
    house: House | None = None
    label: str | None = None


def _shift_back(d: date, years: int) -> date:
    try:
        return d.replace(year=d.year - years)
    except ValueError:  # 2월 29일
        return d.replace(year=d.year - years, day=28)


def default_label(sc: Scenario) -> str:
    return {
        "sell": f"{sc.house_name} 매도",
        "hold_years": f"보유기간 +{sc.years}년",
        "age": f"나이 +{sc.years}세",
        "years_later": f"{sc.years}년 후 (보유·나이 +{sc.years})",
        "price_change": f"{sc.house_name or '전체'} 공시가격 {sc.percent:+g}%" if sc.percent is not None else "공시가격 변동",
        "add_house": f"{sc.house.name if sc.house else '주택'} 추가",
    }[sc.kind]


def apply_scenario(inp: TaxpayerInput, sc: Scenario) -> TaxpayerInput | None:
    """변경안을 적용한 새 입력. 주택이 남지 않으면 None."""
    houses = list(inp.houses)
    update: dict[str, Any] = {}
    names = {h.name for h in houses}

    if sc.kind == "sell":
        if sc.house_name not in names:
            raise ValueError(f"'{sc.house_name}' 주택이 없습니다. 보유 주택: {sorted(names)}")
        houses = [h for h in houses if h.name != sc.house_name]
        if inp.prev_property_tax_base:
            update["prev_property_tax_base"] = {k: v for k, v in inp.prev_property_tax_base.items() if k != sc.house_name}
        if not houses:
            return None
    elif sc.kind in ("hold_years", "age", "years_later"):
        if not sc.years:
            raise ValueError("years가 필요합니다")
        if sc.kind in ("hold_years", "years_later"):
            houses = [h.model_copy(update={"acquired_date": _shift_back(h.acquired_date, sc.years)}) for h in houses]
        if sc.kind in ("age", "years_later"):
            update["birth_date"] = _shift_back(inp.birth_date, sc.years)
    elif sc.kind == "price_change":
        if sc.percent is None:
            raise ValueError("percent가 필요합니다")
        if sc.house_name and sc.house_name not in names:
            raise ValueError(f"'{sc.house_name}' 주택이 없습니다. 보유 주택: {sorted(names)}")
        factor = 1 + D(sc.percent) / 100

        def scale(v: int | None) -> int | None:
            return None if v is None else max(truncate(D(v) * factor, 1000), 1000)

        houses = [h.model_copy(update={"official_price": scale(h.official_price), "market_price": scale(h.market_price)})
                  if not sc.house_name or h.name == sc.house_name else h for h in houses]
    elif sc.kind == "add_house":
        if sc.house is None:
            raise ValueError("추가할 house 정보가 필요합니다")
        if sc.house.name in names:
            raise ValueError(f"'{sc.house.name}' 이름의 주택이 이미 있습니다")
        houses.append(sc.house)

    update["houses"] = houses
    return inp.model_copy(update=update)


def summarize(result: TaxResult | None) -> dict[str, int]:
    """세목 묶음 요약 (재산세 계 = 본세+도시지역분+지방교육세, 종부세 계 = 종부세+농특세)."""
    if result is None:
        return {"property": 0, "comprehensive": 0, "total": 0}
    return {
        "property": result.property_tax_total + result.urban_area_tax + result.local_education_tax,
        "comprehensive": result.comprehensive_tax + result.rural_special_tax,
        "total": result.total,
    }


def compare_scenarios(inp: TaxpayerInput, scenarios: list[Scenario],
                      rules: dict[str, Any] | None = None) -> dict[str, Any]:
    """기준안과 변경안들의 세액을 계산하고 차액을 반환한다."""
    rules = rules or load_rules(inp.tax_year)
    base_result = calculate_total(inp, rules)
    base = summarize(base_result)
    rows = []
    for sc in scenarios:
        new_inp = apply_scenario(inp, sc)
        result = calculate_total(new_inp, rules) if new_inp else None
        s = summarize(result)
        rows.append({
            "label": sc.label or default_label(sc),
            "kind": sc.kind,
            **s,
            "diff_property": s["property"] - base["property"],
            "diff_comprehensive": s["comprehensive"] - base["comprehensive"],
            "diff_total": s["total"] - base["total"],
            "warnings": result.warnings if result else ["보유 주택이 없어 보유세가 0원입니다"],
            "result": result,
        })
    return {"base": {"label": "현재(기준안)", **base, "result": base_result}, "scenarios": rows}
