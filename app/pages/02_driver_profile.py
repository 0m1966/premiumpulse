"""Individual Driver Profile, Scorecard, and Quote Breakdown page."""

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from app.styles import BAND_COLORS, apply_plotly_theme, render_mode_badge
from premiumpulse.db.client_factory import get_current_mode
from premiumpulse.services.pricing_service import PricingService


@st.cache_data(ttl=300)
def get_driver_list():
    service = PricingService()
    return service.list_drivers(limit=100)


def render():
    col1, col2 = st.columns([3, 1])
    with col1:
        st.title("👤 Driver Risk Profile")
        st.caption("30-Day Telematics Scorecard & Quoting Waterfall")
    with col2:
        render_mode_badge(get_current_mode())

    driver_list = get_driver_list()
    if not driver_list:
        st.warning("No driver records found.")
        return

    driver_options = [f"{d['driver_id']} - {d.get('full_name', 'Unknown')}" for d in driver_list]
    selected_option = st.selectbox("Select Driver", driver_options)
    selected_id = selected_option.split(" - ")[0]

    service = PricingService()
    profile = service.get_driver_profile(selected_id)
    score = service.get_driver_score(selected_id)
    quote = service.get_driver_quote(selected_id)
    trips = service.get_driver_trips(selected_id, limit=20)

    if not quote or not score:
        st.error(f"Score or quote details for {selected_id} unavailable.")
        return

    # Top Overview KPIs
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Risk Score", f"{score.risk_score:.1f} / 100")
    band_color = BAND_COLORS.get(score.risk_band.value, "#FFFFFF")
    k2.markdown(
        f"**Risk Band**<br><span style='font-size:1.8rem; font-weight:bold; color:{band_color};'>"
        f"Band {score.risk_band.value}</span>",
        unsafe_allow_html=True,
    )
    k3.metric("Monthly Premium", f"${quote.monthly_premium:.2f}")
    k4.metric("30-Day Driving", f"{score.distance_km:.1f} km")

    st.divider()

    # Factor Penalty Breakdown Chart
    c_chart, c_quote = st.columns([1, 1])

    with c_chart:
        st.subheader("Scorecard Factor Deductions (Points Lost)")
        if score.factor_penalties:
            factor_names = [p.factor_name.replace("_", " ").title() for p in score.factor_penalties]
            deductions = [p.penalty_points for p in score.factor_penalties]
            metrics = [f"{p.metric_value} (Cap: {p.cap_value})" for p in score.factor_penalties]

            fig_p = go.Figure(go.Bar(
                x=deductions,
                y=factor_names,
                orientation="h",
                marker_color="#FF9F1C",
                text=[f"-{d:.1f} pts" for d in deductions],
                textposition="auto",
            ))
            fig_p.update_layout(
                xaxis_title="Penalty Points Deducted (from 100)",
                yaxis=dict(autorange="reversed"),
                height=350,
            )
            apply_plotly_theme(fig_p)
            st.plotly_chart(fig_p, use_container_width=True)

    with c_quote:
        st.subheader("Certified Actuarial Pricing Breakdown")
        bk = quote.breakdown
        st.markdown(f"""
        | Rating Factor | Value | Applied Multiplier |
        | :--- | :--- | :--- |
        | **Vehicle Category Base Rate** | `{quote.vehicle_class.value}` | **${bk.base_rate:.2f}** |
        | **Telematics Risk Band** | `Band {quote.risk_band.value}` | **{bk.band_multiplier:.2f}x** |
        | **Declared Annual Mileage** | `{profile.annual_km_declared:,} km` | **{bk.mileage_factor:.2f}x** |
        | **Vehicle Age** | `{profile.vehicle_age_years} years` | **{bk.vehicle_age_factor:.2f}x** |
        | **Licence Tenure** | `{profile.licence_years} years` | **{bk.experience_factor:.2f}x** |
        | **Calculated Monthly Premium** | `Clamped [$25 - $220]` | **${quote.monthly_premium:.2f}** |
        | **Annual Policy Premium** | `12-Month Total` | **${quote.annual_premium:.2f}** |
        """)

    # Recent 30-Day Trips Table
    st.subheader("Recent Driving Trips (Silver Layer)")
    if trips:
        df_trips = pd.DataFrame(trips)
        show_cols = [
            "trip_id", "trip_start", "trip_end", "distance_km", "duration_min",
            "hard_brake_count", "hard_accel_count", "speeding_seconds", "phone_seconds"
        ]
        st.dataframe(
            df_trips[show_cols],
            use_container_width=True,
            hide_index=True,
            column_config={
                "distance_km": st.column_config.NumberColumn(format="%.1f km"),
                "duration_min": st.column_config.NumberColumn(format="%d min"),
            },
        )


if __name__ == "__main__":
    render()
