"""결과 다운로드: CSV(엑셀 호환), PDF(한글 폰트) (FR-OUT-06)."""
from __future__ import annotations

import csv
import io
import os
from datetime import datetime
from pathlib import Path

from engine.models import TaxResult

DISCLAIMER = "본 결과는 참고용 추정치이며 실제 고지세액과 다를 수 있습니다."

FONT_CANDIDATES = [
    os.environ.get("TAX_SIM_FONT", ""),
    "C:/Windows/Fonts/malgun.ttf",
    "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
    "/System/Library/Fonts/AppleSDGothicNeo.ttc",
    str(Path(__file__).resolve().parent.parent / "assets" / "NanumGothic.ttf"),
]


def summary_rows(result: TaxResult) -> list[tuple[str, int]]:
    return [
        ("재산세 본세", result.property_tax_total),
        ("도시지역분", result.urban_area_tax),
        ("지방교육세", result.local_education_tax),
        ("종합부동산세", result.comprehensive_tax),
        ("농어촌특별세", result.rural_special_tax),
        ("총 보유세", result.total),
    ]


def to_csv_bytes(result: TaxResult) -> bytes:
    """요약 + 계산 근거를 CSV로 (utf-8-sig: 엑셀에서 한글이 깨지지 않음)."""
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["[요약]"])
    w.writerow(["세목", "금액(원)"])
    w.writerows(summary_rows(result))
    w.writerow([])
    w.writerow(["[납부 일정]"])
    w.writerow(["구분", "기간", "금액(원)", "비고"])
    for p in result.payment_schedule:
        w.writerow([p["label"], p.get("period", ""), p["amount"], p.get("installment_note", "")])
    w.writerow([])
    w.writerow(["[계산 근거]"])
    w.writerow(["세목", "단계", "계산식", "값", "근거"])
    for s in result.steps:
        w.writerow([s.tax, s.label, s.formula, s.display_value(), s.basis])
    if result.warnings:
        w.writerow([])
        w.writerow(["[주의]"])
        for msg in result.warnings:
            w.writerow([msg])
    w.writerow([])
    w.writerow([DISCLAIMER])
    return buf.getvalue().encode("utf-8-sig")


def find_korean_font() -> str:
    for path in FONT_CANDIDATES:
        if path and Path(path).exists():
            return path
    raise RuntimeError("PDF용 한글 폰트를 찾을 수 없습니다. TAX_SIM_FONT 환경변수로 .ttf 경로를 지정하세요.")


def to_pdf_bytes(result: TaxResult, title: str = "주택 보유세 예상세액 (2026년 귀속)") -> bytes:
    """요약, 납부 일정, 계산 근거, 면책 문구를 담은 PDF."""
    from fpdf import FPDF
    from fpdf.fonts import FontFace

    pdf = FPDF(format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_font("ko", "", find_korean_font())
    pdf.add_page()
    head = FontFace(fill_color=(230, 236, 245))

    pdf.set_font("ko", size=16)
    pdf.cell(0, 10, title, new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("ko", size=9)
    pdf.cell(0, 6, f"생성일시 {datetime.now():%Y-%m-%d %H:%M} · 과세기준일 2026-06-01", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)

    def section(name: str) -> None:
        pdf.set_font("ko", size=12)
        pdf.cell(0, 8, name, new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("ko", size=9)

    section("1. 요약")
    with pdf.table(col_widths=(60, 50), width=110, align="LEFT", headings_style=head,
                   text_align=("LEFT", "RIGHT")) as t:
        t.row(["세목", "금액"])
        for name, amount in summary_rows(result):
            t.row([name, f"{amount:,}원"])
    pdf.ln(3)

    section("2. 납부 일정")
    with pdf.table(col_widths=(60, 40, 30, 60), headings_style=head, text_align=("LEFT", "LEFT", "RIGHT", "LEFT")) as t:
        t.row(["구분", "기간", "금액", "비고"])
        for p in result.payment_schedule:
            t.row([p["label"], p.get("period", ""), f"{p['amount']:,}원", p.get("installment_note", "")])
    pdf.ln(3)

    section("3. 계산 근거")
    with pdf.table(col_widths=(14, 38, 90, 26, 32), headings_style=head,
                   text_align=("LEFT", "LEFT", "LEFT", "RIGHT", "LEFT")) as t:
        t.row(["세목", "단계", "계산식", "값", "근거"])
        for s in result.steps:
            t.row([s.tax, s.label, s.formula, s.display_value(), s.basis])

    if result.warnings:
        pdf.ln(3)
        section("4. 주의")
        for msg in result.warnings:
            pdf.multi_cell(0, 5, f"- {msg}", new_x="LMARGIN", new_y="NEXT")

    pdf.ln(4)
    pdf.set_font("ko", size=9)
    pdf.multi_cell(0, 5, DISCLAIMER, new_x="LMARGIN", new_y="NEXT")
    return bytes(pdf.output())
