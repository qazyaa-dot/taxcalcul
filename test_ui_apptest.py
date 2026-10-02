"""4단계 검토 버그 수정 회귀 테스트 — 화면 (Streamlit AppTest, 브라우저 없음)."""
from datetime import date
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from engine.models import House, TaxpayerInput

APP = str(Path(__file__).resolve().parent.parent / "app.py")


def field_errors(at) -> list[str]:
    import html
    import re
    return [html.unescape(re.sub(r"<[^>]+>", "", m.value)).replace("⚠", "").strip()
            for m in at.markdown if "field-error" in m.value and "<style>" not in m.value]


def has_result(at) -> bool:
    return any("kpi-grid" in m.value and "<style>" not in m.value for m in at.markdown)


@pytest.fixture
def at(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "")  # .env의 실제 키보다 우선 → 키 없음
    return AppTest.from_file(APP, default_timeout=30).run()


@pytest.mark.parametrize("ratio", [0, 150, -10])
def test_b02_ratio_out_of_range_blocks(at, ratio):
    at.number_input(key="h0_ratio").set_value(ratio).run()
    at.button(key="calc").click().run()
    assert "지분율은 1~100% 사이로 입력하세요" in field_errors(at)
    assert not has_result(at)


def test_b02_acquired_after_assessment_blocks(at):
    at.date_input(key="h0_acquired").set_value(date(2026, 7, 1)).run()
    at.button(key="calc").click().run()
    assert any("과세기준일(2026-06-01) 이전" in e for e in field_errors(at))
    assert not has_result(at)


def test_b02_birth_after_assessment_blocks(at):
    at.date_input(key="tp_birth").set_value(date(2027, 1, 1)).run()
    at.button(key="calc").click().run()
    assert any("생년월일은 과세기준일" in e for e in field_errors(at))


def test_b01_one_house_yes_with_two_houses_blocks(at):
    at.selectbox(key="tp_one_house").select("예 (세대 전체 1주택)").run()
    at.button(key="add_house").click().run()
    at.text_input(key="h1_price").input("5억").run()
    at.button(key="calc").click().run()
    assert any("'예'는 1채일 때만" in e for e in field_errors(at))
    assert not has_result(at)


def test_b01_yes_allowed_when_other_house_excluded(at):
    at.selectbox(key="tp_one_house").select("예 (세대 전체 1주택)").run()
    at.button(key="add_house").click().run()
    at.text_input(key="h1_price").input("1억").run()
    at.checkbox(key="h1_excluded").check().run()
    at.button(key="calc").click().run()
    assert not field_errors(at)
    assert has_result(at)


def test_b04_invalid_input_after_calc_shows_stale_warning(at):
    at.button(key="calc").click().run()
    at.text_input(key="h0_price").input("abc").run()
    assert any("마지막으로 계산한 입력 기준" in w.value for w in at.warning)


def test_b05_new_house_after_calc_has_no_required_error(at):
    at.button(key="calc").click().run()
    at.button(key="add_house").click().run()
    assert field_errors(at) == []
    at.button(key="calc").click().run()  # 다시 계산을 시도하면 그때 표시
    assert "공시가격 또는 실거래가 중 하나는 입력해야 합니다" in field_errors(at)


def test_b08_duplicate_name_error_under_field(at):
    at.button(key="add_house").click().run()
    at.text_input(key="h1_name").input("주택1").run()
    at.text_input(key="h1_price").input("5억").run()
    at.button(key="calc").click().run()
    errs = field_errors(at)
    assert errs.count("다른 주택과 이름이 같습니다. 서로 다른 이름을 입력하세요") == 2  # 두 카드 모두 이름 칸 아래
    assert not has_result(at)


def test_b07_steps_show_units(at):
    at.button(key="calc").click().run()
    df = at.dataframe[-1].value if at.dataframe else None
    steps = [d.value for d in at.dataframe if "단계" in d.value.columns]
    assert steps, "계산 근거 표가 없습니다"
    values = dict(zip(steps[0]["단계"], steps[0]["값"]))
    assert values["과세기준일 만 나이"] == "56세"
    assert values["1세대1주택 판정"] == "예"
    assert values["총 보유세"].endswith("원")
    assert df is not None


def test_b03_confirm_card_refreshes_on_new_parse(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "dummy-not-used")  # AI 탭 렌더링용, API 호출 없음
    at = AppTest.from_file(APP, default_timeout=30).run()
    mk = lambda n, p: TaxpayerInput(birth_date=date(1960, 1, 1), houses=[  # noqa: E731
        House(name=n, official_price=p, acquired_date=date(2014, 1, 1))])
    at.session_state.agent.executor.pending_input = mk("서울 아파트", 2_000_000_000)
    at.run()
    names = [t.value for t in at.text_input if t.label == "주택 이름" and str(t.key).startswith("cf_")]
    assert names == ["서울 아파트"]
    at.session_state.agent.executor.pending_input = mk("부산 아파트", 700_000_000)
    at.run()
    names = [t.value for t in at.text_input if t.label == "주택 이름" and str(t.key).startswith("cf_")]
    prices = [t.value for t in at.text_input if t.label == "공시가격" and str(t.key).startswith("cf_")]
    assert names == ["부산 아파트"]
    assert prices == ["700,000,000"]
