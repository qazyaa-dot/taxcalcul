"""부부 공동명의 1주택 비교 카드."""
from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from engine.joint import compare_joint_ownership
from engine.models import TaxpayerInput

from . import fields
from .format import won


def applicable(inp: TaxpayerInput) -> bool:
    return len(inp.houses) == 1 and inp.houses[0].ownership_ratio < 1


def render_joint(inp: TaxpayerInput) -> None:
    with st.container(border=True):
        st.markdown("**👫 부부 공동명의 비교** — 각자 과세 vs 1세대1주택 특례 신청")
        st.session_state.setdefault("spouse_birth", date(1970, 1, 1))
        spouse = st.date_input("배우자 생년월일", key="spouse_birth", min_value=fields.WIDE_MIN_DATE,
                               max_value=fields.WIDE_MAX_DATE, format="YYYY-MM-DD")
        msg = fields.birth_error(spouse)
        if msg:
            fields.error(msg)
            return
        j = compare_joint_ownership(inp, spouse)
        a, b = j["option_a"], j["option_b"]
        st.dataframe(pd.DataFrame([
            {"방식": a["label"], "본인": won(a["me"]["comprehensive"]), "배우자": won(a["spouse"]["comprehensive"]),
             "종부세+농특세 합계": won(a["comprehensive"])},
            {"방식": f"{b['label']} (납세자: {b['payer']})", "본인": "—", "배우자": "—",
             "종부세+농특세 합계": won(b["comprehensive"])},
        ]), hide_index=True, width="stretch")
        better = a["label"] if j["better"] == "A" else b["label"]
        if j["saving"]:
            st.success(f"**{better}** 방식이 {won(j['saving'])} 유리합니다.", icon=":material/thumb_up:")
        else:
            st.info("두 방식의 종부세가 같습니다.")
        st.caption(j["note"])
