"""입력 위젯 공통: 인라인 오류·힌트, 한국어 금액 입력, 범위 검증.

Streamlit의 min/max 제한은 범위 밖 값을 화면 안내 없이 거부하므로(검토 B-02),
날짜·지분율은 넓은 범위로 받고 여기서 직접 검증해 필드 아래에 오류를 보여준다.
"""
from __future__ import annotations

import html
from datetime import date

import streamlit as st

from engine.models import ASSESSMENT_DATE
from engine.utils import parse_korean_amount

from .format import approx, won

WIDE_MIN_DATE = date(1900, 1, 1)
WIDE_MAX_DATE = date(2100, 12, 31)


def error(msg: str) -> None:
    st.markdown(f'<div class="field-error">⚠ {html.escape(msg)}</div>', unsafe_allow_html=True)


def hint(msg: str) -> None:
    st.markdown(f'<div class="field-hint">{html.escape(msg)}</div>', unsafe_allow_html=True)


def amount_field(container, label: str, key: str, placeholder: str) -> tuple[int | None, str | None]:
    """한국어 금액 입력. (값, 오류) 반환하고 바로 아래에 변환값 또는 오류를 표시."""
    with container:
        txt = st.text_input(label, key=key, placeholder=placeholder)
        if not txt.strip():
            return None, None
        try:
            value = parse_korean_amount(txt)
        except ValueError as e:
            error(str(e))
            return None, str(e)
        if value <= 0:
            error("0보다 큰 금액을 입력하세요")
            return None, "0원"
        hint(f"= {won(value)} ({approx(value)})")
        return value, None


def acquired_error(d: date) -> str | None:
    if d > ASSESSMENT_DATE:
        return "취득일은 과세기준일(2026-06-01) 이전이어야 합니다"
    if d < date(1950, 1, 1):
        return "취득일을 1950-01-01 이후로 입력하세요"
    return None


def birth_error(d: date) -> str | None:
    if d > ASSESSMENT_DATE:
        return "생년월일은 과세기준일(2026-06-01) 이전이어야 합니다"
    if d < date(1900, 1, 1):
        return "생년월일을 다시 확인하세요"
    return None


def ratio_error(v: float) -> str | None:
    if not 1 <= v <= 100:
        return "지분율은 1~100% 사이로 입력하세요"
    return None


def show_if(msg: str | None, errors: list[str]) -> None:
    """오류가 있으면 표시하고 errors에 추가."""
    if msg:
        error(msg)
        errors.append(msg)
