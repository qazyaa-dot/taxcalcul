"""AI 상담 탭: 채팅, 파싱 결과 확인 카드(수정 가능), 예시 질문."""
from __future__ import annotations

import hashlib

import streamlit as st
from pydantic import ValidationError

from agent.client import TaxAgent
from engine.models import House, TaxpayerInput
from engine.utils import parse_korean_amount

from . import fields
from .format import fix_korean_markdown, won
from .input_form import ONE_HOUSE_OPTIONS
from .result_view import render_result

EXAMPLES = [
    "서울 아파트 1채, 공시가 20억, 12년 보유, 만 66세예요. 보유세가 얼마인가요?",
    "아파트 2채(공시가 10억, 7억)를 가지고 있어요. 1채를 팔면 세금이 얼마나 줄어요?",
    "부부 공동명의(50:50) 아파트 공시가 18억이면 단독명의 특례 신청이 유리한가요?",
]


def render_unavailable() -> None:
    with st.container(border=True):
        st.markdown("#### 🤖 AI 상담 (준비 중)")
        st.markdown(
            "말로 설명하면 AI가 입력을 정리하고, 계산 결과를 쉬운 말로 해설해 주는 기능입니다.\n\n"
            "- 예: *“서울 아파트 2채, 공시가 10억·7억, 15년 보유, 만 66세”*\n"
            "- 계산은 항상 시뮬레이터 엔진이 하고, AI는 설명만 합니다.\n"
            "- AI가 말한 금액은 계산 결과와 자동으로 대조합니다.")
        st.info("AI 상담을 쓰려면 `.env`에 `OPENAI_API_KEY`를 설정하세요. "
                "간편 계산과 시나리오 비교는 키 없이 사용할 수 있습니다.", icon=":material/key:")
        st.markdown("**이런 질문을 할 수 있어요**")
        for ex in EXAMPLES:
            st.markdown(f"- {ex}")


def _confirm_card(agent: TaxAgent, pending: TaxpayerInput) -> None:
    """AI가 정리한 입력을 폼으로 보여주고 수정·확정받는다.

    위젯 key에 입력 내용 해시를 넣어, 새 파싱 결과가 오면 이전 값이 남지 않게 한다 (검토 B-03).
    """
    ver = hashlib.md5(pending.model_dump_json().encode()).hexdigest()[:8]
    with st.container(border=True):
        st.markdown("**📝 입력 확인** — AI가 정리한 내용입니다. 틀린 곳을 고친 뒤 계산하세요.")
        with st.form(f"confirm_form_{ver}", border=False):
            b1, b2 = st.columns(2)
            birth = b1.date_input("생년월일", value=pending.birth_date, min_value=fields.WIDE_MIN_DATE,
                                  max_value=fields.WIDE_MAX_DATE, format="YYYY-MM-DD", key=f"cf_{ver}_birth")
            one_house_labels = list(ONE_HOUSE_OPTIONS)
            one_house = b2.selectbox(
                "1세대1주택 여부", one_house_labels, key=f"cf_{ver}_one_house",
                index=list(ONE_HOUSE_OPTIONS.values()).index(pending.is_one_house_household))
            edited = []
            for i, h in enumerate(pending.houses):
                st.markdown(f"**주택 {i + 1}**")
                c1, c2, c3 = st.columns(3)
                name = c1.text_input("주택 이름", value=h.name, key=f"cf_{ver}_name_{i}")
                price = c2.text_input("공시가격", value=f"{h.official_price:,}" if h.official_price else "",
                                      key=f"cf_{ver}_price_{i}")
                market = c3.text_input("실거래가", value=f"{h.market_price:,}" if h.market_price else "",
                                       key=f"cf_{ver}_market_{i}")
                c4, c5, c6 = st.columns(3)
                acquired = c4.date_input("취득일", value=h.acquired_date, min_value=fields.WIDE_MIN_DATE,
                                         max_value=fields.WIDE_MAX_DATE, format="YYYY-MM-DD", key=f"cf_{ver}_acq_{i}")
                ratio = c5.number_input("본인 지분율(%)", value=int(round(h.ownership_ratio * 100)), step=1,
                                        key=f"cf_{ver}_ratio_{i}")
                urban = c6.checkbox("도시지역", value=h.is_urban_area, key=f"cf_{ver}_urban_{i}")
                edited.append((h, name, price, market, acquired, ratio, urban))
            submitted = st.form_submit_button("이 입력으로 계산", type="primary", icon=":material/calculate:")
        if submitted:
            problems = [m for m in [fields.birth_error(birth)] + [
                fields.acquired_error(acq) or fields.ratio_error(r) for _, _, _, _, acq, r, _ in edited] if m]
            if problems:
                st.error("입력 오류: " + "; ".join(problems))
                return
            try:
                houses = [h.model_copy(update={
                    "name": name.strip() or h.name,
                    "official_price": parse_korean_amount(price) if price.strip() else None,
                    "market_price": parse_korean_amount(market) if market.strip() else None,
                    "acquired_date": acquired, "ownership_ratio": ratio / 100, "is_urban_area": urban})
                    for h, name, price, market, acquired, ratio, urban in edited]
                inp = TaxpayerInput(**{**pending.model_dump(), "birth_date": birth,
                                       "is_one_house_household": ONE_HOUSE_OPTIONS[one_house],
                                       "houses": [House(**hh.model_dump()) for hh in houses]})
            except (ValidationError, ValueError) as e:
                st.error(f"입력 오류: {e}")
                return
            with st.spinner("계산하고 해설을 작성하는 중..."):
                reply = agent.confirm_input(inp)
            _record(reply, "(입력 확정 후 계산 요청)")
            st.rerun()


def _record(reply, user_text: str) -> None:
    st.session_state.chat.append({"role": "user", "content": user_text})
    content = reply.error or reply.text
    if reply.guard_failed:
        content = "⚠ " + content
    st.session_state.chat.append({"role": "assistant", "content": content})


def render_ai_tab(agent: TaxAgent) -> None:
    ss = st.session_state
    ss.setdefault("chat", [])
    if not ss.chat:
        st.markdown("**예시 질문**")
        cols = st.columns(len(EXAMPLES))
        for i, (col, ex) in enumerate(zip(cols, EXAMPLES)):
            if col.button(ex, key=f"example_{i}", width="stretch"):
                ss.pending_prompt = ex

    for msg in ss.chat:
        with st.chat_message(msg["role"]):
            st.markdown(fix_korean_markdown(msg["content"]))

    if agent.executor.pending_input is not None:
        _confirm_card(agent, agent.executor.pending_input)

    prompt = st.chat_input("보유 주택과 나이를 설명해 주세요", key="chat_input") or ss.pop("pending_prompt", None)
    if prompt:
        with st.spinner("답변을 작성하는 중..."):
            reply = agent.chat(prompt)
        _record(reply, prompt)
        st.rerun()

    if agent.executor.last_result is not None:
        last_ai = next((m["content"] for m in reversed(ss.chat) if m["role"] == "assistant"), None)
        with st.expander(f"최근 AI 계산 결과 · 총 {won(agent.executor.last_result.total)}", expanded=False):
            render_result(agent.executor.last_result, "ai", ai_text=last_ai, ai_available=True)
