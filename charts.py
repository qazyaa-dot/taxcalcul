"""Plotly 차트."""
from __future__ import annotations

import plotly.graph_objects as go

from .format import won
from .theme import COLORS


def tax_breakdown(result) -> dict[str, int]:
    """시나리오 차트용 세목 묶음: 재산세 본세 / 종부세 본세 / 부가세(도시지역분·지방교육세·농특세)."""
    if result is None:
        return {"재산세": 0, "종부세": 0, "부가세": 0}
    return {
        "재산세": result.property_tax_total,
        "종부세": result.comprehensive_tax,
        "부가세": result.urban_area_tax + result.local_education_tax + result.rural_special_tax,
    }


def scenario_bar(rows: list[dict]) -> go.Figure:
    """rows: [{"label": str, "result": TaxResult | None}, ...] → 세목별 그룹 막대."""
    labels = [r["label"] for r in rows]
    parts = [tax_breakdown(r["result"]) for r in rows]
    fig = go.Figure()
    for name in ("재산세", "종부세", "부가세"):
        values = [p[name] for p in parts]
        fig.add_bar(name=name, x=labels, y=values, marker_color=COLORS[name],
                    hovertemplate="%{x}<br>" + name + ": %{customdata}<extra></extra>",
                    customdata=[won(v) for v in values])
    fig.update_layout(
        barmode="group", height=380, margin=dict(l=10, r=10, t=30, b=10),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
        yaxis=dict(title="원", tickformat=",d"), xaxis=dict(tickangle=0),
        font=dict(family="Noto Sans KR, Malgun Gothic, sans-serif"),
    )
    return fig
