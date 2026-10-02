"""AI 답변 속 금액이 도구 결과와 일치하는지 검증 (PRD 7.4, FR-AI-03)."""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Iterable

from engine.utils import parse_korean_amount

logger = logging.getLogger("tax_agent.guard")

_NUM = r"\d[\d,]*(?:\.\d+)?"
_UNIT = r"(?:조|억|천만|백만|만|천)"
# 숫자+단위 반복(예: "7억 5천만", "15억5000만") 뒤에 선택적으로 "원"
AMOUNT_RE = re.compile(rf"({_NUM}\s*{_UNIT}(?:\s*{_NUM}\s*{_UNIT}?)*|{_NUM})\s*(원)?")
_UNIT_VALUE = {"조": 10**12, "억": 10**8, "천만": 10**7, "백만": 10**6, "만": 10**4, "천": 10**3}


@dataclass
class Amount:
    raw: str
    value: int
    tolerance: int


@dataclass
class GuardReport:
    ok: bool
    checked: list[Amount] = field(default_factory=list)
    mismatches: list[Amount] = field(default_factory=list)


def _tolerance(text: str) -> int:
    """표기 정밀도만큼 허용오차: '123만' → 1만, '5.5억' → 0.1억, '1,234,560원' → 10원(절사)."""
    units = re.findall(_UNIT, text)
    if not units:
        return 10
    tail = re.search(rf"({_NUM})\s*({_UNIT})?\s*$", text)
    if tail is None:
        return _UNIT_VALUE[units[-1]]
    number, unit_name = tail.group(1), tail.group(2)
    if unit_name is None:
        # 단위 뒤에 붙은 맨 숫자: '15억5000'은 만 단위, '3만5000'은 원 단위
        return 10**4 if units[-1] == "억" else 10
    unit = _UNIT_VALUE[unit_name]
    if unit_name == "천" and "억" in units and "만" not in units:
        unit = 10**7  # '7억 5천' = 7억 5천만
    if "." in number:
        return max(int(Decimal(unit) / (10 ** len(number.split(".")[1]))), 1)
    return unit


def extract_amounts(text: str) -> list[Amount]:
    """답변에서 금액 표현을 찾는다. 단위(억·만 등)나 '원'이 붙은 것만 금액으로 본다."""
    found: list[Amount] = []
    for m in AMOUNT_RE.finditer(text):
        body, won = m.group(1), m.group(2)
        has_unit = re.search(_UNIT, body) is not None
        if not (has_unit or won):
            continue
        after = text[m.end():m.end() + 1]
        if not won and after in ("년", "세", "채", "%", "개", "월", "일", "명"):
            continue
        try:
            value = parse_korean_amount(body)
        except ValueError:
            continue
        if value < 1000:
            continue
        found.append(Amount(raw=m.group(0).strip(), value=value, tolerance=_tolerance(body)))
    return found


def collect_numbers(obj: Any, out: set[int] | None = None) -> set[int]:
    """도구 결과(JSON 호환 객체)에 들어 있는 모든 정수 금액을 모은다."""
    out = set() if out is None else out
    if isinstance(obj, bool):
        return out
    if isinstance(obj, int):
        out.add(obj)
    elif isinstance(obj, float) and obj.is_integer():
        out.add(int(obj))
    elif isinstance(obj, dict):
        for v in obj.values():
            collect_numbers(v, out)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            collect_numbers(v, out)
    return out


def check(text: str, known: Iterable[int]) -> GuardReport:
    """답변의 모든 금액이 known 중 하나와 허용오차 안에서 일치하는지 검사."""
    known = sorted(set(known))
    amounts = extract_amounts(text)
    mismatches = [a for a in amounts if not any(abs(a.value - k) <= a.tolerance for k in known)]
    report = GuardReport(ok=not mismatches, checked=amounts, mismatches=mismatches)
    if mismatches:
        logger.warning("금액 불일치 %s", [(a.raw, a.value) for a in mismatches])
    else:
        logger.info("금액 검증 통과 (%d건)", len(amounts))
    return report
