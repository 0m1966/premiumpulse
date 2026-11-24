"""Portfolio Overview page for underwriters and actuaries."""

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from app.styles import BAND_COLORS, apply_plotly_theme, render_mode_badge
from premiumpulse.db.client_factory import get_current_mode
from premiumpulse.services.pricing_service import PricingService


@st.cache_data(ttl=300)
def load_portfolio_data():
    service = PricingService()
    summary = service.get_portfolio_summary()
    drivers = service.list_drivers(limit=100, offset=0)
    return summary, drivers


def render():
    col1, col2 = st.columns([3, 1])
    with col1:
        st.title("📊 Portfolio Overview")
        st.caption("Active Telematics Policyholder Distribution & Premium Yields")
    with col2:
        render_mode_badge(get_current_mode())

    summary, drivers = load_portfolio_data()

    # 4 Metric Cards
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Enrolled Drivers", f"{summary.total_drivers:,}")
    m2.metric("Average Risk Score", f"{summary.average_risk_score:.1f} / 100")
    m3.metric("Average Monthly Premium", f"${summary.average_monthly_premium:.2f}")
    annual_vol = summary.average_monthly_premium * summary.total_drivers * 12
    m4.metric("Total Annual Book", f"${annual_vol:,.0f}")

    st.divider()

    # Visualizations
    v1, v2 = st.columns(2)

    with v1:
        st.subheader("Risk Band Distribution")
        bands = ["A", "B", "C", "D", "E", "UNRATED"]
        counts = [summary.band_distribution.get(b, 0) for b in bands]
        colors = [BAND_COLORS.get(b, "#8B9BB4") for b in bands]

        fig_band = go.Figure(data=[
            go.Bar(
                x=bands,
                y=counts,
                marker_color=colors,
                text=counts,
                textposition="auto",
            )
        ])
        fig_band.update_layout(title="Drivers by Telematics Risk Band", xaxis_title="Risk Band", yaxis_title="Driver Count")
        apply_plotly_theme(fig_band)
        st.plotly_chart(fig_band, use_container_width=True)

    with v2:
        st.subheader("Vehicle Class Segmentation")
        v_classes = list(summary.vehicle_distribution.keys())
        v_counts = list(summary.vehicle_distribution.values())

        fig_veh = go.Figure(data=[
            go.Pie(
                labels=v_classes,
                values=v_counts,
                hole=0.45,
                marker=dict(colors=["#00D2BA", "#2EC4B6", "#FFBF69", "#FF9F1C", "#E71D36"]),
            )
        ])
        fig_veh.update_layout(title="Portfolio by Vehicle Category")
        apply_plotly_theme(fig_veh)
        st.plotly_chart(fig_veh, use_container_width=True)

    # Driver Roster Table
    st.subheader("Driver Policy Roster")
    if drivers:
        df = pd.DataFrame(drivers)
        cols_to_show = [
            "driver_id", "full_name", "city", "vehicle_class",
            "risk_score", "risk_band", "monthly_premium", "annual_premium"
        ]
        available_cols = [c for c in cols_to_show if c in df.columns]
        st.dataframe(
            df[available_cols],
            use_container_width=True,
            hide_index=True,
            column_config={
                "monthly_premium": st.column_config.NumberColumn(format="$%.2f"),
                "annual_premium": st.column_config.NumberColumn(format="$%.2f"),
                "risk_score": st.column_config.NumberColumn(format="%.1f"),
            },
        )


if __name__ == "__main__":
    render()
