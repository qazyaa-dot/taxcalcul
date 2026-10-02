"""에이전트 Tool 정의와 실행 (PRD 7.2). 모든 숫자는 engine이 계산한다."""
from __future__ import annotations

import json
from datetime import date
from typing import Any

from pydantic import ValidationError

from engine.calculator import calculate_total
from engine.comprehensive_tax import calculate_comprehensive_tax
from engine.estimator import estimate_official_price, fill_missing_prices
from engine.joint import compare_joint_ownership
from engine.models import ASSESSMENT_DATE, House, TaxpayerInput, TaxResult
from engine.property_tax import calculate_property_tax
from engine.rules_loader import load_rules
from engine.scenarios import Scenario, compare_scenarios
from engine.utils import parse_korean_amount

from .guard import collect_numbers

_AMOUNT = {"type": "string", "description": "사용자가 말한 금액 표현 그대로 (예: '10억', '7억 5천', '850,000,000')"}

_HOUSE_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string", "description": "주택 이름 (예: '서울 아파트'). 없으면 '주택1' 등"},
        "official_price": {**_AMOUNT, "description": "공시가격. 모르면 생략"},
        "market_price": {**_AMOUNT, "description": "실거래가(시세). 공시가격을 모를 때"},
        "region": {"type": "string", "description": "시·도 (예: 서울)"},
        "is_urban_area": {"type": "boolean", "description": "도시지역 여부. 언급 없으면 생략(기본 true)"},
        "acquired_date": {"type": "string", "description": "취득일 YYYY-MM-DD"},
        "holding_years": {"type": "integer", "description": "보유기간(년). 취득일을 모를 때"},
        "ownership_ratio": {"type": "number", "description": "본인 지분 0~1 (공동명의 50%면 0.5). 기본 1"},
        "house_type": {"type": "string", "enum": ["apartment", "detached", "multi"]},
        "exclude_from_count": {"type": "boolean", "description": "상속주택·지방 저가주택 등 주택 수 제외 특례"},
    },
    "required": ["name"],
}

TOOLS: list[dict[str, Any]] = [
    {
        "name": "parse_user_input",
        "description": (
            "사용자의 자연어 설명에서 추출한 납세자·주택 정보를 검증하고 구조화된 입력으로 변환한다. "
            "금액은 말한 그대로 문자열로 넘긴다. 결과의 status가 incomplete이면 missing_fields를 사용자에게 질문한다."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "birth_date": {"type": "string", "description": "생년월일 YYYY-MM-DD"},
                "age": {"type": "integer", "description": "만 나이. 생년월일을 모를 때"},
                "houses": {"type": "array", "items": _HOUSE_SCHEMA},
                "is_one_house_household": {"type": "boolean", "description": "세대 전체가 1주택인지 사용자가 명시한 경우만"},
                "prev_property_tax": {**_AMOUNT, "description": "전년도 재산세(본세+도시지역분)"},
                "prev_comprehensive_tax": {**_AMOUNT, "description": "전년도 종부세"},
            },
            "required": ["houses"],
        },
    },
    {
        "name": "estimate_official_price",
        "description": "실거래가로 공시가격을 추정한다 (가정 현실화율 적용, 추정치).",
        "input_schema": {
            "type": "object",
            "properties": {"market_price": _AMOUNT,
                           "house_type": {"type": "string", "enum": ["apartment", "detached", "multi"]}},
            "required": ["market_price"],
        },
    },
    {
        "name": "calculate_total",
        "description": "확정된 입력으로 재산세·종부세·부가세 전체와 납부 일정, 단계별 계산 근거를 계산한다.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "calculate_property_tax",
        "description": "확정된 입력으로 주택별 재산세(본세·도시지역분·지방교육세)만 계산한다.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "calculate_comprehensive_tax",
        "description": "확정된 입력으로 종합부동산세·농어촌특별세만 계산한다.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "compare_scenarios",
        "description": (
            "확정된 입력을 기준안으로 What-if 변경안의 세액과 차액(diff_*)을 계산한다. "
            "kind: sell(house_name 매도), hold_years(보유 +years년), age(나이 +years세), "
            "years_later(보유·나이 모두 +years), price_change(percent% 변동, house_name 없으면 전체), add_house(house 추가)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "scenarios": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "kind": {"type": "string",
                                     "enum": ["sell", "hold_years", "age", "years_later", "price_change", "add_house"]},
                            "house_name": {"type": "string"},
                            "years": {"type": "integer"},
                            "percent": {"type": "number"},
                            "house": _HOUSE_SCHEMA,
                            "label": {"type": "string"},
                        },
                        "required": ["kind"],
                    },
                },
            },
            "required": ["scenarios"],
        },
    },
    {
        "name": "compare_joint_ownership",
        "description": "부부 공동명의 1주택일 때 '공동명의 각자 과세'와 '1세대1주택 특례 신청'의 종부세를 비교한다.",
        "input_schema": {
            "type": "object",
            "properties": {"spouse_birth_date": {"type": "string", "description": "배우자 생년월일 YYYY-MM-DD"}},
            "required": ["spouse_birth_date"],
        },
    },
    {
        "name": "get_tax_rule",
        "description": (
            "2026년 세법 규칙 값을 조회한다. key 예: property_tax.fair_market_ratio, property_tax.standard_rates, "
            "property_tax.one_house_special_rates, comprehensive_tax.deduction, comprehensive_tax.rates_upto_2, "
            "comprehensive_tax.rates_3plus, comprehensive_tax.senior_credit, comprehensive_tax.long_term_credit, "
            "comprehensive_tax.burden_cap_rate, sources"
        ),
        "input_schema": {"type": "object", "properties": {"key": {"type": "string"}}, "required": ["key"]},
    },
]


class ToolError(Exception):
    """도구 실행 실패 (모델에게 is_error로 전달)."""


def _shift_years(d: date, years: int) -> date:
    try:
        return d.replace(year=d.year - years)
    except ValueError:
        return d.replace(year=d.year - years, day=28)


def result_payload(result: TaxResult) -> dict[str, Any]:
    """모델에게 돌려줄 계산 결과 (간결한 JSON)."""
    return {
        "summary": {
            "total": result.total,
            "property_tax": result.property_tax_total,
            "urban_area_tax": result.urban_area_tax,
            "local_education_tax": result.local_education_tax,
            "property_tax_group_total": result.property_tax_total + result.urban_area_tax + result.local_education_tax,
            "comprehensive_tax": result.comprehensive_tax,
            "rural_special_tax": result.rural_special_tax,
            "comprehensive_group_total": result.comprehensive_tax + result.rural_special_tax,
            "effective_rate_percent": round(result.effective_rate * 100, 4),
        },
        "houses": [h.model_dump() for h in result.property_tax_by_house],
        "payment_schedule": result.payment_schedule,
        "steps": [{"tax": s.tax, "label": s.label, "formula": s.formula, "value": s.value, "basis": s.basis}
                  for s in result.steps],
        "warnings": result.warnings,
    }


class ToolExecutor:
    """도구 실행기. 확정 입력(current_input)과 대기 입력(pending_input)을 세션 상태로 보관한다."""

    def __init__(self, rules: dict[str, Any] | None = None):
        self.rules = rules or load_rules(2026)
        self.current_input: TaxpayerInput | None = None
        self.pending_input: TaxpayerInput | None = None
        self.known_numbers: set[int] = collect_numbers(self.rules)
        self.last_result: TaxResult | None = None

    # ---- 상태 ----
    def confirm(self, inp: TaxpayerInput) -> None:
        self.current_input = inp
        self.pending_input = None
        collect_numbers(inp.model_dump(mode="json"), self.known_numbers)

    def _require_input(self) -> TaxpayerInput:
        if self.current_input is None:
            raise ToolError("아직 확정된 입력이 없습니다. parse_user_input 후 사용자가 화면에서 입력을 확정해야 계산할 수 있습니다.")
        return self.current_input

    # ---- 실행 ----
    def execute(self, name: str, args: dict[str, Any]) -> tuple[str, bool]:
        """(JSON 문자열, is_error)를 반환. 결과 숫자는 known_numbers에 기록한다."""
        handler = getattr(self, f"_tool_{name}", None)
        if handler is None:
            return json.dumps({"error": f"알 수 없는 도구: {name}"}, ensure_ascii=False), True
        try:
            payload = handler(args or {})
        except (ToolError, ValueError, ValidationError) as e:
            return json.dumps({"error": str(e)}, ensure_ascii=False), True
        collect_numbers(payload, self.known_numbers)
        return json.dumps(payload, ensure_ascii=False, default=str), False

    def _amount(self, v: Any) -> int | None:
        return None if v in (None, "") else parse_korean_amount(v)

    def _tool_parse_user_input(self, args: dict[str, Any]) -> dict[str, Any]:
        missing: list[str] = []
        assumptions: list[str] = []
        birth = args.get("birth_date")
        if not birth and args.get("age") is not None:
            birth = date(ASSESSMENT_DATE.year - int(args["age"]), 1, 1).isoformat()
            assumptions.append(f"만 {args['age']}세 → 생년월일을 {birth}로 가정")
        if not birth:
            missing.append("생년월일 또는 만 나이")

        houses = []
        raw_houses = args.get("houses") or []
        if not raw_houses:
            missing.append("보유 주택 정보")
        for i, h in enumerate(raw_houses, 1):
            name = h.get("name") or f"주택{i}"
            official = self._amount(h.get("official_price"))
            market = self._amount(h.get("market_price"))
            if official is None and market is None:
                missing.append(f"{name}: 공시가격 또는 실거래가")
            acquired = h.get("acquired_date")
            if not acquired and h.get("holding_years") is not None:
                acquired = _shift_years(ASSESSMENT_DATE, int(h["holding_years"])).isoformat()
                assumptions.append(f"{name}: 보유 {h['holding_years']}년 → 취득일을 {acquired}로 가정")
            if not acquired:
                missing.append(f"{name}: 취득일 또는 보유기간")
            ratio = h.get("ownership_ratio", 1.0)
            if ratio is not None and ratio > 1:
                ratio = ratio / 100  # 50 → 0.5
            houses.append({k: v for k, v in {
                "name": name, "official_price": official, "market_price": market,
                "region": h.get("region") or "서울", "is_urban_area": h.get("is_urban_area", True),
                "acquired_date": acquired, "ownership_ratio": ratio or 1.0,
                "house_type": h.get("house_type") or "apartment",
                "exclude_from_count": bool(h.get("exclude_from_count", False)),
            }.items() if v is not None})

        data = {
            "birth_date": birth, "houses": houses,
            "is_one_house_household": args.get("is_one_house_household"),
            "prev_property_tax": self._amount(args.get("prev_property_tax")),
            "prev_comprehensive_tax": self._amount(args.get("prev_comprehensive_tax")),
        }
        if missing:
            return {"status": "incomplete", "missing_fields": missing, "partial_input": data, "assumptions": assumptions}
        inp = TaxpayerInput(**data)
        self.pending_input = inp
        return {"status": "complete", "parsed_input": inp.model_dump(mode="json"), "assumptions": assumptions,
                "next": "사용자가 화면의 입력 확인 카드에서 확정하면 계산 도구를 사용할 수 있습니다."}

    def _tool_estimate_official_price(self, args: dict[str, Any]) -> dict[str, Any]:
        return estimate_official_price(parse_korean_amount(args["market_price"]),
                                       args.get("house_type", "apartment"), self.rules)

    def _tool_calculate_total(self, args: dict[str, Any]) -> dict[str, Any]:
        self.last_result = calculate_total(self._require_input(), self.rules)
        return result_payload(self.last_result)

    def _filled_input(self) -> tuple[TaxpayerInput, list[str]]:
        inp, _, warnings = fill_missing_prices(self._require_input(), self.rules)
        return inp, warnings

    def _tool_calculate_property_tax(self, args: dict[str, Any]) -> dict[str, Any]:
        inp, warnings = self._filled_input()
        r = calculate_property_tax(inp, self.rules)
        return {**r.model_dump(), "warnings": warnings + r.warnings}

    def _tool_calculate_comprehensive_tax(self, args: dict[str, Any]) -> dict[str, Any]:
        inp, warnings = self._filled_input()
        r = calculate_comprehensive_tax(inp, calculate_property_tax(inp, self.rules), self.rules)
        return {**r.model_dump(), "warnings": warnings + r.warnings}

    def _tool_compare_scenarios(self, args: dict[str, Any]) -> dict[str, Any]:
        scenarios = []
        for raw in args.get("scenarios", []):
            raw = dict(raw)
            if raw.get("house"):
                h = dict(raw["house"])
                for k in ("official_price", "market_price"):
                    if h.get(k) not in (None, ""):
                        h[k] = parse_korean_amount(h[k])
                if not h.get("acquired_date"):
                    h["acquired_date"] = _shift_years(ASSESSMENT_DATE, int(h.pop("holding_years", 0) or 0)).isoformat()
                h.pop("holding_years", None)
                raw["house"] = House(**h)
            scenarios.append(Scenario(**raw))
        out = compare_scenarios(self._require_input(), scenarios, self.rules)
        strip = lambda d: {k: v for k, v in d.items() if k != "result"}  # noqa: E731
        return {"base": strip(out["base"]), "scenarios": [strip(s) for s in out["scenarios"]],
                "note": "현행 2026년 세법을 그대로 적용한 비교입니다."}

    def _tool_compare_joint_ownership(self, args: dict[str, Any]) -> dict[str, Any]:
        out = compare_joint_ownership(self._require_input(), date.fromisoformat(args["spouse_birth_date"]), self.rules)
        out.pop("results")
        return out

    def _tool_get_tax_rule(self, args: dict[str, Any]) -> dict[str, Any]:
        node: Any = self.rules
        for part in str(args.get("key", "")).split("."):
            if not isinstance(node, dict) or part not in node:
                raise ToolError(f"규칙 키를 찾을 수 없습니다: {args.get('key')}")
            node = node[part]
        return {"key": args["key"], "value": node, "tax_year": self.rules["tax_year"], "sources": self.rules["sources"]}
