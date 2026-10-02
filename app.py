"""주택 보유세 시뮬레이터 (2026년 귀속) — Streamlit 진입점."""
import logging
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

from agent.client import TaxAgent, api_key_available
from engine import calculate_total
from ui import joint_view
from ui.ai_chat import render_ai_tab, render_unavailable
from ui.export import DISCLAIMER
from ui.input_form import render_input_form
from ui.result_view import render_result
from ui.scenario_view import render_scenario_tab
from ui.theme import inject_css

# .env는 앱 폴더 → 상위 폴더 순으로 찾는다 (이미 설정된 환경변수는 덮어쓰지 않음)
for _env in (Path(__file__).with_name(".env"), Path(__file__).resolve().parent.parent / ".env"):
    if _env.exists():
        load_dotenv(_env)
        break
logging.basicConfig(level=logging.INFO)
logging.getLogger("fontTools").setLevel(logging.WARNING)  # PDF 폰트 서브셋 로그 억제

st.set_page_config(page_title="주택 보유세 시뮬레이터", page_icon="🏠", layout="wide")
inject_css()

ss = st.session_state
ss.setdefault("form_input", None)
ss.setdefault("form_result", None)
if "agent" not in ss:
    ss.agent = TaxAgent()
ai_ready = api_key_available()

with st.sidebar:
    st.markdown("### 🏠 보유세 시뮬레이터")
    st.markdown('<span class="badge badge-info">2026년 귀속</span><span class="badge badge-info">과세기준일 2026.6.1</span>',
                unsafe_allow_html=True)
    st.markdown("**사용 방법**\n"
                "1. 간편 계산에서 나이와 보유 주택을 입력하고 계산합니다.\n"
                "2. 결과의 '계산 근거 보기'에서 단계별 계산식을 확인합니다.\n"
                "3. 시나리오 비교로 매도·보유기간 변화의 효과를 봅니다.")
    st.toggle("2027년 개편안 비교 (준비 중)", value=False, disabled=True, key="reform_toggle",
              help="2026년 8월 발표된 세제개편안은 국회 심의 중이라 아직 반영하지 않습니다.")
    st.markdown(f'<span class="badge {"badge-ok" if ai_ready else "badge-warn"}">AI 상담 '
                f'{"사용 가능" if ai_ready else "API 키 미설정"}</span>', unsafe_allow_html=True)
    st.divider()
    st.markdown(f'<div class="disclaimer">⚠ {DISCLAIMER}<br>세율 등 일부 값은 시행령 확인이 필요한 가정값을 포함합니다.</div>',
                unsafe_allow_html=True)

st.markdown('<div class="app-header"><h1>주택 보유세 시뮬레이터</h1>'
            '<p>재산세·종합부동산세 예상세액을 계산하고 계산 근거를 단계별로 보여드립니다.</p></div>',
            unsafe_allow_html=True)

tab_form, tab_ai, tab_scn = st.tabs([":material/calculate: 간편 계산", ":material/smart_toy: AI 상담",
                                     ":material/bar_chart: 시나리오 비교"])

with tab_form:
    inp, clicked = render_input_form()
    if clicked and inp is not None:
        ss.form_input, ss.form_result = inp, calculate_total(inp)
    if ss.form_result is not None:
        st.divider()
        if inp is None:
            st.warning("입력에 오류가 있습니다. 아래 결과는 마지막으로 계산한 입력 기준입니다. "
                       "오류를 고친 뒤 [계산하기]를 누르세요.", icon=":material/history:")
        elif inp != ss.form_input:
            st.info("입력이 바뀌었습니다. 아래 결과는 마지막으로 계산한 입력 기준입니다. "
                    "다시 계산하려면 [계산하기]를 누르세요.", icon=":material/history:")
        render_result(ss.form_result, "form", ai_available=ai_ready)
        if joint_view.applicable(ss.form_input):
            joint_view.render_joint(ss.form_input)

with tab_ai:
    if ai_ready:
        render_ai_tab(ss.agent)
    else:
        render_unavailable()

with tab_scn:
    render_scenario_tab(ss.form_input)

st.divider()
st.markdown(f'<div class="disclaimer">⚠ {DISCLAIMER}</div>', unsafe_allow_html=True)
