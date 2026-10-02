"""최소 CSS. 색은 반투명 배경 + 상속 글자색을 써서 라이트·다크 모드 모두 읽히게 한다."""
import streamlit as st

ACCENT = "#1E40AF"
COLORS = {"재산세": "#1E40AF", "종부세": "#0F766E", "부가세": "#D97706"}

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;500;700&display=swap');
html, body, .stApp { font-family: 'Noto Sans KR', 'Malgun Gothic', 'Apple SD Gothic Neo', sans-serif; }
.block-container { padding-top: 2rem; max-width: 1200px; }

.app-header h1 { font-size: 1.7rem; margin: 0 0 .2rem 0; }
.app-header p { margin: 0; opacity: .72; font-size: .92rem; }

.kpi-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 12px; margin: .4rem 0 1rem; }
.kpi { border: 1px solid rgba(128,128,128,.28); border-left: 4px solid #1E40AF; border-radius: 10px;
       padding: 12px 16px; background: rgba(30,64,175,.06); }
.kpi.primary { background: rgba(30,64,175,.13); }
.kpi.teal { border-left-color: #0F766E; background: rgba(15,118,110,.07); }
.kpi.amber { border-left-color: #D97706; background: rgba(217,119,6,.07); }
.kpi .label { font-size: .82rem; opacity: .75; }
.kpi .value { font-size: 1.45rem; font-weight: 700; line-height: 1.35; word-break: keep-all; }
.kpi .sub { font-size: .8rem; opacity: .7; }

.timeline { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 12px; margin-bottom: 1rem; }
.tl-item { border: 1px solid rgba(128,128,128,.28); border-radius: 10px; padding: 12px 14px; position: relative; }
.tl-item .month { display: inline-block; font-weight: 700; font-size: .8rem; padding: 2px 10px; border-radius: 999px;
                  background: rgba(30,64,175,.14); margin-bottom: 6px; }
.tl-item .amount { font-size: 1.15rem; font-weight: 700; }
.tl-item .desc, .tl-item .note { font-size: .8rem; opacity: .75; }
.tl-item .note { margin-top: 4px; opacity: .9; }

.badge { display: inline-block; padding: 1px 9px; border-radius: 999px; font-size: .75rem; font-weight: 600;
         margin-right: 4px; vertical-align: middle; }
.badge-warn { background: rgba(245,158,11,.22); border: 1px solid rgba(245,158,11,.55); }
.badge-info { background: rgba(30,64,175,.14); border: 1px solid rgba(30,64,175,.35); }
.badge-ok { background: rgba(15,118,110,.16); border: 1px solid rgba(15,118,110,.4); }

.warn-list { margin: -.3rem 0 1rem; }
.warn-line { font-size: .86rem; margin: .2rem 0; }
.field-error { color: #E5484D; font-size: .8rem; margin-top: -.6rem; margin-bottom: .4rem; }
.field-hint { font-size: .8rem; opacity: .7; margin-top: -.6rem; margin-bottom: .4rem; }
.disclaimer { font-size: .8rem; opacity: .7; }
.ai-box { border: 1px dashed rgba(128,128,128,.45); border-radius: 10px; padding: 12px 16px; font-size: .9rem; margin-bottom: 1rem; }

@media (max-width: 640px) {
  .app-header h1 { font-size: 1.35rem; }
  .kpi .value { font-size: 1.2rem; }
  .block-container { padding-left: 1rem; padding-right: 1rem; }
}
</style>
"""


def inject_css() -> None:
    st.markdown(CSS, unsafe_allow_html=True)
