"""결과 영역: KPI 카드, 세목별 상세표, 납부 일정, 계산 근거, AI 해설, 다운로드."""
from __future__ import annotations

import html

import pandas as pd
import streamlit as st

from engine.models import TaxResult

from .export import to_csv_bytes, to_pdf_bytes
from .format import approx, pct, won, won_full


def _kpi(label: str, value: int, sub: str, cls: str = "") -> str:
    return (f'<div class="kpi {cls}"><div class="label">{label}</div>'
            f'<div class="value">{won(value)}</div><div class="sub">{sub}</div></div>')


def render_kpis(result: TaxResult) -> None:
    prop = result.property_tax_total + result.urban_area_tax + result.local_education_tax
    comp = result.comprehensive_tax + result.rural_special_tax
    price_sum = sum(h.official_price * h.ownership_ratio for h in result.property_tax_by_house)
    cards = [
        _kpi("총 보유세", result.total, approx(result.total), "primary"),
        _kpi("재산세 합계", prop, "본세 + 도시지역분 + 지방교육세"),
        _kpi("종부세 합계", comp, "종부세 + 농어촌특별세" if comp else "과세 대상 아님", "teal"),
        f'<div class="kpi amber"><div class="label">실효세율</div><div class="value">{pct(result.effective_rate)}</div>'
        f'<div class="sub">공시가격 합계 {approx(int(price_sum))} 대비</div></div>',
    ]
    st.markdown(f'<div class="kpi-grid">{"".join(cards)}</div>', unsafe_allow_html=True)


def render_warnings(result: TaxResult) -> None:
    if not result.warnings:
        return
    lines = "".join(
        f'<div class="warn-line"><span class="badge badge-warn">{"추정치" if "추정" in w else "확인 필요"}</span>'
        f'{html.escape(w)}</div>' for w in result.warnings)
    st.markdown(f'<div class="warn-list">{lines}</div>', unsafe_allow_html=True)


def render_detail_table(result: TaxResult) -> None:
    rows = [
        ("재산세", "재산세 본세", result.property_tax_total),
        ("재산세", "도시지역분", result.urban_area_tax),
        ("재산세", "지방교육세", result.local_education_tax),
        ("종부세", "종합부동산세", result.comprehensive_tax),
        ("종부세", "농어촌특별세", result.rural_special_tax),
        ("합계", "총 보유세", result.total),
    ]
    st.dataframe(pd.DataFrame([{"구분": g, "세목": n, "금액": won_full(v)} for g, n, v in rows]),
                 hide_index=True, width="stretch")

    houses = []
    for h in result.property_tax_by_house:
        notes = []
        if h.price_estimated:
            notes.append("공시가격 추정치")
        if h.special_rate_applied:
            notes.append("1주택 특례세율")
        if h.ownership_ratio < 1:
            notes.append(f"지분 {h.ownership_ratio * 100:g}%")
        houses.append({
            "주택": h.name, "공시가격": won(h.official_price), "공정시장가액비율": f"{h.fair_market_ratio * 100:g}%",
            "과세표준": won(h.tax_base), "재산세 계": won(h.total), "비고": ", ".join(notes),
        })
    st.markdown("**주택별 재산세**")
    st.dataframe(pd.DataFrame(houses), hide_index=True, width="stretch")


def render_timeline(result: TaxResult) -> None:
    items = []
    for p in result.payment_schedule:
        note = p.get("installment_note") or ""
        if p["amount"] == 0 and p["month"] == 9:
            note = "7월에 일괄 납부 (20만 원 이하)" if result.property_tax_total else ""
        if p["amount"] == 0 and p["month"] == 12:
            note = "종부세 과세 대상 아님"
        items.append(
            f'<div class="tl-item"><span class="month">{p["month"]}월</span>'
            f'<div class="amount">{won(p["amount"])}</div>'
            f'<div class="desc">{html.escape(p["label"])}<br>{html.escape(p.get("period", ""))}</div>'
            + (f'<div class="note">ℹ {html.escape(note)}</div>' if note else "") + "</div>")
    st.markdown(f'<div class="timeline">{"".join(items)}</div>', unsafe_allow_html=True)


def render_steps(result: TaxResult, key: str) -> None:
    with st.expander("계산 근거 보기 (단계별 계산식·근거 조문)"):
        df = pd.DataFrame([{"세목": s.tax, "단계": s.label, "계산식": s.formula, "값": s.display_value(),
                            "근거": s.basis} for s in result.steps])
        st.dataframe(df, hide_index=True, width="stretch", key=f"steps_{key}",
                     column_config={"계산식": st.column_config.TextColumn(width="large")})


def render_ai_box(ai_text: str | None, ai_available: bool) -> None:
    st.markdown("**🤖 AI 해설**")
    if ai_text:
        st.markdown(ai_text)
    elif ai_available:
        st.markdown('<div class="ai-box">AI 상담 탭에서 이 결과에 대해 질문할 수 있습니다.</div>', unsafe_allow_html=True)
    else:
        st.markdown('<div class="ai-box">AI 해설을 쓰려면 API 키를 설정하세요. '
                    '키가 없어도 위 계산 결과와 계산 근거는 그대로 확인할 수 있습니다.</div>', unsafe_allow_html=True)


def render_downloads(result: TaxResult, key: str) -> None:
    d1, d2 = st.columns(2)
    d1.download_button("CSV 다운로드", to_csv_bytes(result), "보유세_계산결과.csv", "text/csv",
                       key=f"csv_{key}", icon=":material/table_view:", width="stretch")
    try:
        pdf = to_pdf_bytes(result)
    except RuntimeError as e:
        d2.caption(str(e))
    else:
        d2.download_button("PDF 다운로드", pdf, "보유세_계산결과.pdf", "application/pdf",
                           key=f"pdf_{key}", icon=":material/picture_as_pdf:", width="stretch")


def render_result(result: TaxResult, key: str, ai_text: str | None = None, ai_available: bool = False) -> None:
    """결과 영역 전체."""
    st.subheader("계산 결과")
    render_kpis(result)
    render_warnings(result)
    left, right = st.columns([3, 2], gap="large")
    with left:
        st.markdown("**세목별 상세**")
        render_detail_table(result)
    with right:
        st.markdown("**납부 일정**")
        render_timeline(result)
    render_steps(result, key)
    render_ai_box(ai_text, ai_available)
    render_downloads(result, key)
