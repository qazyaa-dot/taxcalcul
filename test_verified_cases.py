"""PRD 12.1 검증 케이스. expected는 위택스·홈택스 모의계산 결과로 채운다 (null이면 skip)."""
import json
from pathlib import Path

import pytest

from engine.calculator import calculate_total
from engine.models import TaxpayerInput

CASES = json.loads((Path(__file__).parent / "cases" / "verified_cases.json").read_text(encoding="utf-8"))["cases"]
TOLERANCE = 0.01


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_verified_case(case):
    inp = TaxpayerInput(**case["input"])
    expected = case.get("expected")
    result = calculate_total(inp)  # 입력이 엔진에서 오류 없이 계산되는지 항상 확인
    if not expected:
        pytest.skip("위택스/홈택스 검증값 필요")
    for key, value in expected.items():
        actual = getattr(result, key)
        assert abs(actual - value) <= max(abs(value) * TOLERANCE, 10), f"{key}: {actual} vs {value}"
