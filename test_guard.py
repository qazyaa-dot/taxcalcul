"""AI 답변 금액 검증 가드."""
import pytest

from agent.guard import check, collect_numbers, extract_amounts

KNOWN = {5_506_560, 2_970_000, 568_800, 113_760, 2_000_000_000, 1_200_000_000, 480_000_000, 1_234_560}


@pytest.mark.parametrize("text, value", [
    ("총 5,506,560원입니다", 5_506_560),
    ("약 551만 원", 5_510_000),
    ("20억 원", 2_000_000_000),
    ("기본공제 12억", 1_200_000_000),
    ("과세표준 4.8억", 480_000_000),
    ("7억 5천", 750_000_000),
])
def test_extract(text, value):
    assert extract_amounts(text)[0].value == value


def test_non_amounts_ignored():
    assert extract_amounts("만 66세, 보유 12년, 세율 0.7%, 2026년 6월 1일, 1세대1주택, 3채") == []


def test_all_match():
    text = "총 보유세는 5,506,560원(약 551만 원)이고 종부세는 568,800원, 농특세 113,760원입니다. 공시가 20억에서 12억을 공제합니다."
    report = check(text, KNOWN)
    assert report.ok, report.mismatches
    assert len(report.checked) == 6


def test_mismatch_detected():
    report = check("종부세는 600,000원입니다", KNOWN)
    assert not report.ok
    assert report.mismatches[0].value == 600_000


def test_rounded_approx_tolerance():
    assert check("약 123만 원", {1_234_560}).ok
    assert not check("약 130만 원", {1_234_560}).ok


def test_collect_numbers():
    assert collect_numbers({"a": 1, "b": [2, {"c": 3.0}], "d": True, "e": "4"}) == {1, 2, 3}


def test_negative_diff_quoted_as_decrease():
    """시나리오 차액 -227,520은 답변에서 '227,520원 감소'로 쓰여도 통과해야 한다 (실제 API 응답에서 발견)."""
    known = collect_numbers({"diff_comprehensive": -227_520, "comprehensive": 455_040})
    assert check("종부세가 227,520원 줄어 455,040원이 됩니다", known).ok
