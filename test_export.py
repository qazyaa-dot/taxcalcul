"""CSV/PDF 다운로드."""
from datetime import date

import pytest

from engine.calculator import calculate_total
from ui.export import find_korean_font, to_csv_bytes, to_pdf_bytes


@pytest.fixture
def result(make_input):
    return calculate_total(make_input([2_000_000_000], birth=date(1960, 3, 1), acquired=date(2014, 1, 1)))


def test_csv(result):
    data = to_csv_bytes(result)
    assert data.startswith(b"\xef\xbb\xbf")  # utf-8-sig
    text = data.decode("utf-8-sig")
    assert "총 보유세,5506560" in text
    assert "재산세 중복분 공제" in text
    assert "참고용 추정치" in text


def test_pdf(result):
    try:
        find_korean_font()
    except RuntimeError:
        pytest.skip("한글 폰트 없음")
    data = to_pdf_bytes(result)
    assert data.startswith(b"%PDF")
    assert len(data) > 5000
