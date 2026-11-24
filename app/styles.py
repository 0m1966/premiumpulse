"""Shared visual styling, Plotly dark theme, and metric card helpers for Streamlit."""

import plotly.graph_objects as go
import streamlit as st

THEME_BG = "#0A1128"
THEME_CARD_BG = "#131F42"
THEME_PRIMARY = "#00D2BA"
THEME_TEXT = "#FFFFFF"
THEME_MUTED = "#8B9BB4"
THEME_ACCENT_ORANGE = "#FF9F1C"
THEME_ACCENT_RED = "#E71D36"
THEME_ACCENT_GREEN = "#2EC4B6"

BAND_COLORS = {
    "A": "#2EC4B6",  # Teal / Emerald
    "B": "#00D2BA",  # Primary Teal
    "C": "#FFBF69",  # Soft Yellow
    "D": "#FF9F1C",  # Orange
    "E": "#E71D36",  # Coral Red
    "UNRATED": "#8B9BB4",  # Gray
}


def apply_plotly_theme(fig: go.Figure) -> go.Figure:
    """Apply consistent high-contrast dark theme to any Plotly figure."""
    fig.update_layout(
        paper_bgcolor=THEME_CARD_BG,
        plot_bgcolor=THEME_CARD_BG,
        font=dict(color=THEME_TEXT, family="sans-serif", size=12),
        margin=dict(l=20, r=20, t=40, b=20),
        legend=dict(
            font=dict(color=THEME_TEXT),
            bgcolor="rgba(0,0,0,0)",
        ),
    )
    fig.update_xaxes(
        gridcolor="#22335E",
        zerolinecolor="#22335E",
        tickfont=dict(color=THEME_MUTED),
        title_font=dict(color=THEME_TEXT),
    )
    fig.update_yaxes(
        gridcolor="#22335E",
        zerolinecolor="#22335E",
        tickfont=dict(color=THEME_MUTED),
        title_font=dict(color=THEME_TEXT),
    )
    return fig


def render_mode_badge(mode: str) -> None:
    """Render distinctive top-right badge indicating Live or Snapshot mode."""
    if mode == "LIVE":
        st.markdown(
            '<div style="display:inline-block; padding: 4px 12px; border-radius: 12px; '
            'background-color: #0E4438; color: #00D2BA; border: 1px solid #00D2BA; font-weight: bold; font-size: 0.85rem;">'
            '🟢 LIVE MODE (Snowflake Mart)</div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            '<div style="display:inline-block; padding: 4px 12px; border-radius: 12px; '
            'background-color: #172B57; color: #58A6FF; border: 1px solid #58A6FF; font-weight: bold; font-size: 0.85rem;">'
            '🔵 SNAPSHOT MODE (Offline Bundled SQLite)</div>',
            unsafe_allow_html=True,
        )
