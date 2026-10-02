"""연도별 세법 규칙(JSON) 로드와 검증."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

RULES_DIR = Path(__file__).resolve().parent.parent / "rules"

_REQUIRED = {
    "rounding": ["base_unit", "tax_unit"],
    "estimation": ["realization_rate"],
    "property_tax": [
        "fair_market_ratio", "standard_rates", "one_house_special_rates",
        "base_cap_rate", "urban_area_rate", "local_education_rate", "lump_sum_threshold",
    ],
    "comprehensive_tax": [
        "deduction", "fair_market_ratio", "rates_upto_2", "rates_3plus", "heavy_house_count",
        "property_tax_overlap", "senior_credit", "long_term_credit", "credit_cap",
        "burden_cap_rate", "rural_special_rate", "installment",
    ],
}


class RulesError(ValueError):
    """규칙 파일 형식 오류."""


def _validate_brackets(brackets: list, where: str) -> None:
    """[상한, 세율] 구간표: 마지막 상한은 null, 상한은 오름차순."""
    if not brackets or brackets[-1][0] is not None:
        raise RulesError(f"{where}: 마지막 구간의 상한은 null이어야 합니다")
    uppers = [b[0] for b in brackets[:-1]]
    if uppers != sorted(uppers):
        raise RulesError(f"{where}: 구간 상한이 오름차순이 아닙니다")


def validate_rules(rules: dict[str, Any]) -> None:
    """필수 키와 구간표 형식을 검사한다."""
    for section, keys in _REQUIRED.items():
        if section not in rules:
            raise RulesError(f"'{section}' 섹션이 없습니다")
        missing = [k for k in keys if k not in rules[section]]
        if missing:
            raise RulesError(f"'{section}'에 필수 키가 없습니다: {missing}")
    pt, ct = rules["property_tax"], rules["comprehensive_tax"]
    _validate_brackets(pt["standard_rates"]["brackets"], "property_tax.standard_rates")
    _validate_brackets(pt["one_house_special_rates"]["brackets"], "property_tax.one_house_special_rates")
    _validate_brackets(ct["rates_upto_2"]["brackets"], "comprehensive_tax.rates_upto_2")
    _validate_brackets(ct["rates_3plus"]["brackets"], "comprehensive_tax.rates_3plus")
    if pt["fair_market_ratio"]["one_house"]["brackets"][-1]["max_price"] is not None:
        raise RulesError("1세대1주택 공정시장가액비율 마지막 구간의 max_price는 null이어야 합니다")


@lru_cache(maxsize=8)
def load_rules(tax_year: int = 2026) -> dict[str, Any]:
    """rules/tax_rules_<연도>.json을 읽어 검증 후 반환한다."""
    path = RULES_DIR / f"tax_rules_{tax_year}.json"
    if not path.exists():
        raise RulesError(f"{tax_year}년 세법 규칙 파일이 없습니다: {path.name}")
    rules = json.loads(path.read_text(encoding="utf-8"))
    validate_rules(rules)
    return rules
