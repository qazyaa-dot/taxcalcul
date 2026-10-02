"""간편 계산 입력 폼: 납세자 카드 + 주택 카드(추가/삭제). 입력 오류는 필드 바로 아래 표시."""
from __future__ import annotations

from datetime import date

import streamlit as st
from pydantic import ValidationError

from engine.models import House, TaxpayerInput

from . import fields

MAX_HOUSES = 10
REGIONS = ["서울", "경기", "인천", "부산", "대구", "광주", "대전", "울산", "세종",
           "강원", "충북", "충남", "전북", "전남", "경북", "경남", "제주"]
HOUSE_TYPES = {"아파트": "apartment", "단독주택": "detached", "다세대·연립": "multi"}
ONE_HOUSE_OPTIONS = {"자동 판정": None, "예 (세대 전체 1주택)": True, "아니오": False}


def init_state() -> None:
    ss = st.session_state
    if "house_ids" not in ss:
        ss.house_ids = [0]
        ss.next_house_id = 1
        _init_house(0, first=True)
    ss.setdefault("tp_birth", date(1970, 1, 1))
    ss.setdefault("tp_one_house", "자동 판정")
    ss.setdefault("tp_prev_prop", "")
    ss.setdefault("tp_prev_comp", "")


def _init_house(hid: int, first: bool = False) -> None:
    ss = st.session_state
    defaults = {
        "name": f"주택{len(ss.house_ids)}", "region": "서울", "type": "아파트",
        "price": "9억" if first else "", "market": "", "acquired": date(2015, 1, 1),
        "ratio": 100, "urban": True, "excluded": False,
    }
    for k, v in defaults.items():
        ss.setdefault(f"h{hid}_{k}", v)


def _add_house() -> None:
    ss = st.session_state
    if len(ss.house_ids) >= MAX_HOUSES:
        return
    hid = ss.next_house_id
    ss.next_house_id += 1
    ss.house_ids.append(hid)
    _init_house(hid)


def _remove_house(hid: int) -> None:
    ss = st.session_state
    if len(ss.house_ids) > 1:
        ss.house_ids.remove(hid)
        for k in [k for k in ss.keys() if str(k).startswith(f"h{hid}_")]:
            del ss[k]


def _request_calc() -> None:
    ss = st.session_state
    ss.calc_requested = True
    ss.required_ids = set(ss.house_ids)  # 필수 항목 오류는 계산을 시도한 시점의 카드에만 표시 (B-05)


def _counted_ids() -> list[int]:
    """화면 체크 상태 기준 주택 수 산정 대상 (엔진 household.counted_houses와 같은 규칙)."""
    ss = st.session_state
    ids = [hid for hid in ss.house_ids if not ss.get(f"h{hid}_excluded", False)]
    return ids or list(ss.house_ids)


def _house_card(hid: int, idx: int, show_required: bool, duplicate: bool) -> tuple[dict | None, list[str]]:
    ss = st.session_state
    errors: list[str] = []
    with st.container(border=True):
        # 가로 컨테이너는 모바일에서도 줄바꿈하지 않는다 (B-09)
        with st.container(horizontal=True, horizontal_alignment="distribute", vertical_alignment="center"):
            st.markdown(f"**🏠 주택 {idx}**")
            st.button("삭제", key=f"h{hid}_delete", on_click=_remove_house, args=(hid,),
                      disabled=len(ss.house_ids) <= 1, type="tertiary", icon=":material/delete:", width="content")

        c1, c2, c3 = st.columns(3)
        with c1:
            name = st.text_input("주택 이름", key=f"h{hid}_name")
            if not name.strip():
                fields.show_if("주택 이름을 입력하세요", errors)
            elif duplicate:
                fields.show_if("다른 주택과 이름이 같습니다. 서로 다른 이름을 입력하세요", errors)
        c2.selectbox("소재지(시·도)", REGIONS, key=f"h{hid}_region")
        c3.selectbox("주택 유형", list(HOUSE_TYPES), key=f"h{hid}_type")

        c4, c5 = st.columns(2)
        official, e1 = fields.amount_field(c4, "공시가격", f"h{hid}_price", "예: 9억 5천만")
        market, e2 = fields.amount_field(c5, "실거래가 (공시가격을 모를 때)", f"h{hid}_market", "예: 13억")
        errors += [e for e in (e1, e2) if e]
        if official is None and market is None and not (e1 or e2) and show_required:
            with c4:
                fields.show_if("공시가격 또는 실거래가 중 하나는 입력해야 합니다", errors)
        elif official is None and market is not None:
            with c5:
                st.markdown('<span class="badge badge-warn">추정치</span> 실거래가로 공시가격을 추정합니다',
                            unsafe_allow_html=True)

        c6, c7 = st.columns(2)
        with c6:
            acquired = st.date_input("취득일", key=f"h{hid}_acquired", min_value=fields.WIDE_MIN_DATE,
                                     max_value=fields.WIDE_MAX_DATE, format="YYYY-MM-DD",
                                     help="과세기준일(2026-06-01) 이전이어야 합니다")
            fields.show_if(fields.acquired_error(acquired), errors)
        with c7:
            ratio = st.number_input("본인 지분율(%)", step=1, key=f"h{hid}_ratio",
                                    help="공동명의면 본인 지분만 입력 (예: 50)")
            fields.show_if(fields.ratio_error(ratio), errors)

        c8, c9 = st.columns(2)
        c8.checkbox("도시지역 주택", key=f"h{hid}_urban", help="도시지역분(과세표준 × 0.14%) 부과 대상")
        c9.checkbox("주택 수 제외 특례", key=f"h{hid}_excluded",
                    help="상속주택·지방 저가주택 등. 다른 주택이 있을 때만 적용됩니다")

    data = dict(
        name=name.strip(), official_price=official, market_price=market,
        region=ss[f"h{hid}_region"], house_type=HOUSE_TYPES[ss[f"h{hid}_type"]],
        acquired_date=acquired, ownership_ratio=ratio / 100,
        is_urban_area=ss[f"h{hid}_urban"], exclude_from_count=ss[f"h{hid}_excluded"],
    )
    return (None if errors else data), errors


def render_input_form() -> tuple[TaxpayerInput | None, bool]:
    """폼을 그리고 (입력, 계산 버튼 눌림)을 반환한다. 오류가 있으면 입력은 None."""
    init_state()
    ss = st.session_state
    required_ids = ss.get("required_ids", set())
    errors: list[str] = []

    with st.container(border=True):
        st.markdown("**👤 납세자 정보**")
        c1, c2 = st.columns(2)
        with c1:
            birth = st.date_input("생년월일", key="tp_birth", min_value=fields.WIDE_MIN_DATE,
                                  max_value=fields.WIDE_MAX_DATE, format="YYYY-MM-DD",
                                  help="고령자 세액공제는 2026-06-01 기준 만 나이로 판정")
            fields.show_if(fields.birth_error(birth), errors)
        with c2:
            st.selectbox("1세대1주택 여부", list(ONE_HOUSE_OPTIONS), key="tp_one_house",
                         help="자동 판정: 아래 주택 중 주택 수 산정 대상이 1채면 1세대1주택")
            counted = len(_counted_ids())
            if ONE_HOUSE_OPTIONS[ss.tp_one_house] is True and counted != 1:  # B-01
                fields.show_if(f"주택 수 산정 대상이 {counted}채입니다. '예'는 1채일 때만 선택할 수 있습니다", errors)
        with st.expander("선택 입력 · 세부담상한용 전년도 세액"):
            p1, p2 = st.columns(2)
            prev_prop, e1 = fields.amount_field(p1, "전년도 재산세 (본세+도시지역분)", "tp_prev_prop", "예: 250만")
            prev_comp, e2 = fields.amount_field(p2, "전년도 종부세", "tp_prev_comp", "예: 80만")
            errors += [e for e in (e1, e2) if e]

    names = [str(ss.get(f"h{hid}_name", "")).strip() for hid in ss.house_ids]
    duplicates = {n for n in names if n and names.count(n) > 1}  # B-08: 해당 이름 칸 아래에 표시
    houses = []
    for idx, hid in enumerate(list(ss.house_ids), 1):
        data, errs = _house_card(hid, idx, hid in required_ids, names[idx - 1] in duplicates)
        errors += errs
        if data:
            houses.append(data)

    b1, b2 = st.columns([1, 2])
    b1.button("주택 추가", key="add_house", on_click=_add_house, icon=":material/add:",
              disabled=len(ss.house_ids) >= MAX_HOUSES, width="stretch")
    b2.button("계산하기", key="calc", type="primary", icon=":material/calculate:",
              width="stretch", on_click=_request_calc)
    # 콜백이 먼저 실행되므로 이번 실행에서 필수 항목 오류가 이미 필드 아래에 표시된다
    clicked = ss.pop("calc_requested", False)

    if errors:
        if clicked:
            st.error("입력값을 확인해 주세요. 오류가 있는 항목 아래에 안내가 표시됩니다.")
        return None, clicked
    try:
        inp = TaxpayerInput(
            birth_date=birth, houses=[House(**h) for h in houses],
            is_one_house_household=ONE_HOUSE_OPTIONS[ss.tp_one_house],
            prev_property_tax=prev_prop, prev_comprehensive_tax=prev_comp)
    except ValidationError as e:
        if clicked:
            st.error("입력값을 확인해 주세요: " + "; ".join(err["msg"] for err in e.errors()))
        return None, clicked
    return inp, clicked
