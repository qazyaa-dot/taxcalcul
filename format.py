"""화면 금액·비율 표기 통일."""
from __future__ import annotations


def won(n: int) -> str:
    """1234560 → '1,234,560원'."""
    return f"{int(n):,}원"


def approx(n: int) -> str:
    """보조 표기: 1234560 → '약 123만 원', 950000000 → '약 9.5억 원'."""
    n = int(n)
    if n >= 100_000_000:
        eok = n / 100_000_000
        txt = f"{eok:.2f}".rstrip("0").rstrip(".")
        return f"약 {txt}억 원"
    if n >= 10_000:
        return f"약 {round(n / 10_000):,}만 원"
    return f"{n:,}원"


def won_full(n: int) -> str:
    """'1,234,560원 (약 123만 원)'. 1만 원 미만은 보조 표기 생략."""
    return won(n) if abs(int(n)) < 10_000 else f"{won(n)} ({approx(n)})"


def signed_won(n: int) -> str:
    """차액 표기: '+1,234원' / '−1,234원' / '0원'."""
    n = int(n)
    if n > 0:
        return f"+{n:,}원"
    if n < 0:
        return f"−{abs(n):,}원"
    return "0원"


def pct(rate: float, digits: int = 2) -> str:
    """0.001234 → '0.12%'."""
    return f"{rate * 100:.{digits}f}%"
