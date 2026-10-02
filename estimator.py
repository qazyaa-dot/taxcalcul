"""실거래가 기반 공시가격 추정 (FR-IN-06)."""
from __future__ import annotations

from typing import Any

from .models import CalculationStep, TaxpayerInput
from .rules_loader import load_rules
from .utils import D, pct, truncate, won


def realization_rate(house_type: str, rules: dict[str, Any]) -> float:
    rates = rules["estimation"]["realization_rate"]
    return rates.get(house_type, rates["default"])


def estimate_official_price(market_price: int, house_type: str = "apartment",
                            rules: dict[str, Any] | None = None) -> dict[str, Any]:
    """실거래가 × 가정 현실화율 → 추정 공시가격 (천 원 미만 절사)."""
    rules = rules or load_rules()
    rate = realization_rate(house_type, rules)
    return {
        "market_price": market_price,
        "realization_rate": rate,
        "estimated_official_price": truncate(D(market_price) * D(rate), 1000),
    }


def fill_missing_prices(
    inp: TaxpayerInput, rules: dict[str, Any] | None = None,
) -> tuple[TaxpayerInput, list[CalculationStep], list[str]]:
    """공시가격이 없는 주택을 추정치로 채운 새 입력과, 추정 단계·경고를 반환한다."""
    rules = rules or load_rules(inp.tax_year)
    steps: list[CalculationStep] = []
    warnings: list[str] = []
    houses = []
    for h in inp.houses:
        if h.official_price is None:
            est = estimate_official_price(h.market_price, h.house_type, rules)
            h = h.model_copy(update={"official_price": est["estimated_official_price"], "price_estimated": True})
            steps.append(CalculationStep(
                tax="공통", label=f"[{h.name}] 공시가격 추정",
                formula=f"실거래가 {won(est['market_price'])} × 가정 현실화율 {pct(est['realization_rate'])}",
                value=h.official_price, basis="추정치 (공시가격알리미에서 실제 공시가격 확인 권장)"))
            warnings.append(f"{h.name}: 공시가격을 입력하지 않아 실거래가로 추정했습니다 (추정치)")
        houses.append(h)
    return inp.model_copy(update={"houses": houses}), steps, warnings
