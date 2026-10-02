"""시나리오 비교 탭."""
from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from engine.models import House, TaxpayerInput
from engine.scenarios import Scenario, compare_scenarios
from engine.utils import parse_korean_amount

from . import fields
from .charts import scenario_bar
from .format import signed_won, won


def _build_scenarios(base: TaxpayerInput) -> tuple[list[Scenario], list[str]]:
    errors: list[str] = []
    names = [h.name for h in base.houses]
    c1, c2, c3 = st.columns(3)
    sell = c1.multiselect("매도할 주택", names, key="scn_sell", help="선택한 주택마다 별도 시나리오로 비교")
    with c2:
        years = st.number_input("N년 후 (보유·나이 +N)", step=1, key="scn_years", help="0~30년. 0이면 비교하지 않음")
        if not 0 <= years <= 30:
            fields.error("0~30 사이로 입력하세요")
            errors.append("N년 범위")
    with c3:
        pct = st.number_input("공시가격 변동(%)", step=5, key="scn_pct",
                              help="-50~100%. 전체 주택 공시가격을 함께 변동. 0이면 비교하지 않음")
        if not -50 <= pct <= 100:
            fields.error("-50~100 사이로 입력하세요")
            errors.append("변동률 범위")
    scenarios = [Scenario(kind="sell", house_name=s) for s in sell]
    if years and not errors:
        scenarios.append(Scenario(kind="years_later", years=int(years)))
    if pct and not errors:
        scenarios.append(Scenario(kind="price_change", percent=float(pct)))

    with st.expander("주택 추가 시나리오"):
        a1, a2, a3 = st.columns(3)
        add_name = a1.text_input("추가 주택 이름", key="scn_add_name", placeholder="예: 지방 아파트")
        add_price = a2.text_input("추가 주택 공시가격", key="scn_add_price", placeholder="예: 3억")
        a3.date_input("취득일", key="scn_add_date", min_value=fields.WIDE_MIN_DATE, max_value=fields.WIDE_MAX_DATE,
                      format="YYYY-MM-DD")
        if add_name.strip() or add_price.strip():
            try:
                if not add_name.strip() or add_name.strip() in names:
                    raise ValueError("기존 주택과 다른 이름을 입력하세요")
                if fields.acquired_error(st.session_state.scn_add_date):
                    raise ValueError(fields.acquired_error(st.session_state.scn_add_date))
                house = House(name=add_name.strip(), official_price=parse_korean_amount(add_price),
                              acquired_date=st.session_state.scn_add_date)
                scenarios.append(Scenario(kind="add_house", house=house))
            except ValueError as e:
                errors.append(f"주택 추가: {e}")
    return scenarios, errors


def render_scenario_tab(base: TaxpayerInput | None) -> None:
    st.markdown("현재 입력(기준안)과 변경안의 보유세를 **현행 2026년 세법**으로 비교합니다.")
    if base is None:
        st.info("먼저 '간편 계산' 탭에서 계산하면 그 입력을 기준안으로 비교할 수 있습니다.", icon=":material/info:")
        return
    fingerprint = base.model_dump_json()
    if st.session_state.get("scn_base") != fingerprint:  # 기준안이 바뀌면 이전 비교 결과는 버린다
        st.session_state.scn_base = fingerprint
        st.session_state.pop("scn_output", None)
        if "scn_sell" in st.session_state:
            names = {h.name for h in base.houses}
            st.session_state.scn_sell = [s for s in st.session_state.scn_sell if s in names]
    st.session_state.setdefault("scn_years", 5)
    st.session_state.setdefault("scn_pct", 0)
    st.session_state.setdefault("scn_add_date", date(2026, 1, 1))

    scenarios, errors = _build_scenarios(base)
    for e in errors:
        st.error(e)
    run = st.button("비교하기", key="scn_run", type="primary", icon=":material/compare_arrows:",
                    disabled=not scenarios or bool(errors))
    if not scenarios:
        st.caption("비교할 변경안을 하나 이상 선택하세요.")
    if run:
        st.session_state.scn_output = compare_scenarios(base, scenarios)

    out = st.session_state.get("scn_output")
    if not out:
        return
    rows = [out["base"]] + out["scenarios"]
    st.plotly_chart(scenario_bar(rows), key="scn_chart", width="stretch")
    st.dataframe(pd.DataFrame([{
        "시나리오": r["label"], "재산세 합계": won(r["property"]), "종부세 합계": won(r["comprehensive"]),
        "총 보유세": won(r["total"]),
        "기준안 대비": "—" if r is out["base"] else signed_won(r["diff_total"]),
    } for r in rows]), hide_index=True, width="stretch")
    st.caption("재산세 합계 = 본세+도시지역분+지방교육세, 종부세 합계 = 종부세+농어촌특별세. "
               "N년 후 비교도 현행 세법·현재 공시가격 기준입니다.")
