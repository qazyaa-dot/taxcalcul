"""공통 계산 유틸: 누진세율, 절사, 금액 표기."""
from __future__ import annotations

import re
from decimal import ROUND_DOWN, Decimal


def D(x: float | int | str) -> Decimal:
    """float 오차 없이 Decimal로 변환."""
    return Decimal(str(x))


def progressive_tax(amount: Decimal | int, brackets: list) -> Decimal:
    """한계세율 구간표 [[상한, 세율], ..., [None, 세율]]로 누진세액을 계산한다."""
    amount = D(amount)
    tax = Decimal(0)
    lower = Decimal(0)
    for upper, rate in brackets:
        if amount <= lower:
            break
        top = amount if upper is None else min(amount, D(upper))
        tax += (top - lower) * D(rate)
        if upper is None:
            break
        lower = D(upper)
    return tax


def truncate(x: Decimal | int | float, unit: int) -> int:
    """unit 미만 절사 (예: unit=10 → 10원 미만 버림)."""
    x = D(x)
    if x <= 0:
        return 0
    return int((x / unit).quantize(Decimal(1), rounding=ROUND_DOWN)) * unit


_SMALL_UNITS = {"천": 1000, "백": 100, "십": 10}
_AMOUNT_RE = re.compile(r"^[0-9.,]*$")


def _parse_below_man(text: str) -> Decimal:
    """'5천3백', '5000', '1.5천' 같은 1만 미만 단위 표현을 숫자로."""
    if not text:
        return Decimal(0)
    total = Decimal(0)
    num = ""
    for ch in text:
        if ch.isdigit() or ch == ".":
            num += ch
        elif ch in _SMALL_UNITS:
            total += (D(num) if num else Decimal(1)) * _SMALL_UNITS[ch]
            num = ""
        else:
            raise ValueError(f"해석할 수 없는 금액 표현: {text}")
    if num:
        total += D(num)
    return total


def parse_korean_amount(value: str | int | float) -> int:
    """한국어 금액 표현을 원 단위 정수로 변환한다.

    예: "10억" → 1,000,000,000 / "7억 5천" → 750,000,000 (억 뒤의 천·백은 천만·백만)
        "15억5000만원" → 1,550,000,000 / "15억5000" → 1,550,000,000 / "3,500만" → 35,000,000
    """
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if value < 0:
            raise ValueError("금액은 음수일 수 없습니다")
        return int(value)
    text = str(value).strip().replace(" ", "").replace(",", "").replace("원", "")
    for prefix in ("약", "대략", "공시가", "공시가격", "실거래가"):
        if text.startswith(prefix):
            text = text[len(prefix):]
    if not text:
        raise ValueError("금액이 비어 있습니다")
    if text.startswith("-"):
        raise ValueError("금액은 음수일 수 없습니다")
    if _AMOUNT_RE.match(text):
        return int(D(text))

    total = Decimal(0)
    rest = text
    if "조" in rest:
        head, rest = rest.split("조", 1)
        total += _parse_below_man(head) * 10**12
    had_eok = "억" in rest
    if had_eok:
        head, rest = rest.split("억", 1)
        total += (_parse_below_man(head) if head else Decimal(1)) * 10**8
    if "만" in rest:
        head, rest = rest.split("만", 1)
        total += (_parse_below_man(head) if head else Decimal(1)) * 10**4
        total += _parse_below_man(rest)
    elif had_eok and rest:
        # 억 뒤에 만 없이 오는 숫자·천·백은 만 단위로 본다 ("7억 5천", "15억5000")
        total += _parse_below_man(rest) * 10**4
    else:
        total += _parse_below_man(rest)
    return int(total)


def won(n: int | Decimal) -> str:
    """천 단위 콤마 금액 표기."""
    return f"{int(n):,}원"


def pct(r: float | Decimal) -> str:
    """비율을 % 문자열로 (0.0014 → 0.14%)."""
    return f"{float(r) * 100:g}%"
