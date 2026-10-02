"""화면 금액 표기."""
import pytest

from ui.format import approx, fix_korean_markdown, pct, signed_won, won, won_full


@pytest.mark.parametrize("n, expected", [
    (1_234_560, "약 123만 원"), (950_000_000, "약 9.5억 원"), (2_000_000_000, "약 20억 원"),
    (1_512_000, "약 151만 원"), (9_999, "9,999원"),
])
def test_approx(n, expected):
    assert approx(n) == expected


def test_won_full():
    assert won_full(1_234_560) == "1,234,560원 (약 123만 원)"
    assert won_full(0) == "0원"
    assert won(5_506_560) == "5,506,560원"


def test_signed_and_pct():
    assert signed_won(1234) == "+1,234원"
    assert signed_won(-1234) == "−1,234원"
    assert signed_won(0) == "0원"
    assert pct(0.001234) == "0.12%"


def test_fix_korean_markdown():
    """실제 OpenAI 응답에서 발견: '**[이 입력으로 계산]**을'은 굵게 처리되지 않고 별표가 보인다."""
    assert fix_korean_markdown("**[이 입력으로 계산]**을 눌러") == "[**이 입력으로 계산**]을 눌러"
    assert fix_korean_markdown("**5,506,560원**입니다") == "**5,506,560원**입니다"  # 정상 표기는 그대로
