"""부부 공동명의 1주택: 각자 과세 vs 1세대1주택 특례 신청 비교 (PRD 4장 P1, TC-10)."""
from __future__ import annotations

from datetime import date
from typing import Any

from .calculator import calculate_total
from .household import counted_houses
from .models import TaxpayerInput
from .rules_loader import load_rules
from .scenarios import summarize


def compare_joint_ownership(inp: TaxpayerInput, spouse_birth_date: date,
                            rules: dict[str, Any] | None = None) -> dict[str, Any]:
    """본인 지분 주택 1채를 배우자와 공동명의(나머지 지분)로 보유한 경우 두 방식의 세액을 비교한다.

    A. 공동명의 각자 과세: 각자 지분 공시가격에서 9억 공제, 세액공제 없음
    B. 1세대1주택 특례 신청: 지분이 큰 사람(같으면 본인)이 주택 전체를 단독 소유한 것으로 보고 12억 공제 + 고령자·장기보유 공제
    """
    rules = rules or load_rules(inp.tax_year)
    counted = counted_houses(inp.houses)
    if len(inp.houses) != 1 or len(counted) != 1 or counted[0].ownership_ratio >= 1:
        raise ValueError("공동명의 비교는 지분 100% 미만인 주택 1채만 보유한 경우에 사용할 수 있습니다")
    house = counted[0]
    my_ratio = house.ownership_ratio
    spouse_ratio = round(1 - my_ratio, 6)

    mine = calculate_total(inp, rules)
    spouse_inp = inp.model_copy(update={
        "birth_date": spouse_birth_date,
        "houses": [house.model_copy(update={"ownership_ratio": spouse_ratio})],
        "prev_property_tax": None, "prev_comprehensive_tax": None, "prev_property_tax_base": None,
    })
    spouse = calculate_total(spouse_inp, rules)
    a_mine, a_spouse = summarize(mine), summarize(spouse)
    option_a = {
        "label": "공동명의 각자 과세",
        "me": a_mine, "spouse": a_spouse,
        "comprehensive": a_mine["comprehensive"] + a_spouse["comprehensive"],
        "total": a_mine["total"] + a_spouse["total"],
    }

    payer_is_me = my_ratio >= spouse_ratio
    full_inp = inp.model_copy(update={
        "birth_date": inp.birth_date if payer_is_me else spouse_birth_date,
        "houses": [house.model_copy(update={"ownership_ratio": 1.0})],
        "is_one_house_household": True,
        "prev_property_tax": None, "prev_comprehensive_tax": None,
    })
    full = calculate_total(full_inp, rules)
    b = summarize(full)
    option_b = {
        "label": "1세대1주택 특례 신청",
        "payer": "본인" if payer_is_me else "배우자",
        "comprehensive": b["comprehensive"],
        "total": b["total"],
        "senior_and_long_term_applied": any(s.label == "1세대1주택자 세액공제" for s in full.steps),
    }

    diff = option_a["comprehensive"] - option_b["comprehensive"]
    return {
        "house": house.name,
        "my_ratio": my_ratio,
        "spouse_ratio": spouse_ratio,
        "option_a": option_a,
        "option_b": option_b,
        "better": "B" if diff > 0 else "A",
        "saving": abs(diff),
        "note": ("종부세(농특세 포함) 기준 비교이며 재산세는 두 방식이 같습니다(지분별 절사 차이 제외). "
                 "특례는 매년 9.16~9.30에 관할 세무서에 신청해야 적용됩니다."),
        "results": {"me": mine, "spouse": spouse, "special": full},
    }
