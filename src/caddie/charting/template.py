"""Shared Plotly template for all Caddie-generated charts.

Registers a named template with plotly.io.templates so any chart built with
`template="caddie"` (or via `set_as_default`) picks up consistent colors,
fonts, and layout defaults, independent of any connector or analytics skill.
"""

import plotly.graph_objects as go
import plotly.io as pio

TEMPLATE_NAME = "caddie"

_COLORWAY = [
    "#3E6D9C",
    "#7A9E7E",
    "#D98E5B",
    "#B45F5F",
    "#8C6BB1",
    "#5A9BA6",
    "#C9A34E",
    "#6B7280",
]

_FONT_FAMILY = "Helvetica Neue, Arial, sans-serif"

caddie_template = go.layout.Template(
    layout=go.Layout(
        colorway=_COLORWAY,
        font=dict(family=_FONT_FAMILY, size=13, color="#1F2937"),
        title=dict(font=dict(size=18)),
        paper_bgcolor="#FFFFFF",
        plot_bgcolor="#FFFFFF",
        xaxis=dict(
            gridcolor="#E5E7EB",
            zerolinecolor="#E5E7EB",
            linecolor="#D1D5DB",
        ),
        yaxis=dict(
            gridcolor="#E5E7EB",
            zerolinecolor="#E5E7EB",
            linecolor="#D1D5DB",
        ),
        legend=dict(bgcolor="rgba(0,0,0,0)"),
        margin=dict(l=60, r=30, t=60, b=50),
    )
)


def register(set_as_default: bool = True) -> None:
    """Register the Caddie template with plotly.io.templates.

    Safe to call more than once (re-registers the same template).
    """
    pio.templates[TEMPLATE_NAME] = caddie_template
    if set_as_default:
        pio.templates.default = TEMPLATE_NAME


register()
