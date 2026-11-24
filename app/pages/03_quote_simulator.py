"""Interactive What-If Driving Behavior and Premium Simulator."""

from decimal import Decimal
import streamlit as st

from app.styles import BAND_COLORS, render_mode_badge
from premiumpulse.db.client_factory import get_current_mode
from premiumpulse.domain.models import QuoteSimulationRequest
from premiumpulse.services.pricing_service import PricingService


def render():
    col1, col2 = st.columns([3, 1])
    with col1:
        st.title("🎛️ What-If Policy Quote Simulator")
        st.caption("Interactive Telematics Behavioral Adjustment & Projected Savings")
    with col2:
        render_mode_badge(get_current_mode())

    service = PricingService()
    driver_list = service.list_drivers(limit=100)
    if not driver_list:
        st.warning("No driver records found.")
        return

    driver_options = [f"{d['driver_id']} - {d.get('full_name', 'Unknown')}" for d in driver_list]
    selected_option = st.selectbox("Select Baseline Driver", driver_options)
    selected_id = selected_option.split(" - ")[0]

    baseline_quote = service.get_driver_quote(selected_id)
    baseline_score = service.get_driver_score(selected_id)

    if not baseline_quote or not baseline_score:
        st.error("Driver data unavailable.")
        return

    st.divider()

    # Sliders for Behavioral Adjustments
    st.subheader("Adjust Driving Habits & Exposure")
    c1, c2, c3 = st.columns(3)

    with c1:
        sim_hb = st.slider(
            "Hard Brakes per 100 km",
            min_value=0.0,
            max_value=25.0,
            value=float(baseline_score.hard_brake_per_100km),
            step=0.5,
            help="Threshold <= -3.0 m/s^2 deceleration. Cap is 15/100km.",
        )
        sim_ha = st.slider(
            "Hard Accelerations per 100 km",
            min_value=0.0,
            max_value=20.0,
            value=float(baseline_score.hard_accel_per_100km),
            step=0.5,
            help="Threshold >= +3.0 m/s^2 acceleration. Cap is 12/100km.",
        )

    with c2:
        sim_speeding = st.slider(
            "Speeding (% of Driving Time)",
            min_value=0.0,
            max_value=50.0,
            value=float(baseline_score.speeding_pct),
            step=1.0,
            help="Time spent > 10 km/h above posted limit. Cap is 20%.",
        )
        sim_phone = st.slider(
            "Phone Usage (min per 100 km)",
            min_value=0.0,
            max_value=45.0,
            value=float(baseline_score.phone_min_per_100km),
            step=1.0,
            help="Screen/call interaction while vehicle in motion. Cap is 30 min/100km.",
        )

    with c3:
        sim_night = st.slider(
            "Night Driving (% of Time between 0-4 AM)",
            min_value=0.0,
            max_value=40.0,
            value=float(baseline_score.night_pct),
            step=1.0,
            help="High-risk nocturnal driving percentage. Cap is 25%.",
        )
        sim_annual_km = st.select_slider(
            "Annual Kilometers Declared",
            options=[6000, 10000, 14000, 18000, 24000, 32000],
            value=14000,
            help="Actuarial exposure tiers: Tier 1 (<=8k), Tier 2 (<=15k), Tier 3 (<=25k), Tier 4 (>25k).",
        )

    # Run Simulation
    req = QuoteSimulationRequest(
        driver_id=selected_id,
        hard_brake_per_100km=sim_hb,
        hard_accel_per_100km=sim_ha,
        speeding_pct=sim_speeding,
        night_pct=sim_night,
        phone_min_per_100km=sim_phone,
        annual_km_declared=sim_annual_km,
    )
    res = service.simulate_quote(req)

    st.divider()

    # Results Comparison Card
    st.subheader("Projected Policyholder Impact")
    r1, r2, r3, r4 = st.columns(4)

    r1.metric(
        "Projected Score",
        f"{res.projected_risk_score:.1f}",
        delta=f"{res.score_delta:+.1f} pts",
    )

    proj_band_color = BAND_COLORS.get(res.projected_risk_band.value, "#FFFFFF")
    r2.markdown(
        f"**Projected Band**<br><span style='font-size:1.6rem; font-weight:bold; color:{proj_band_color};'>"
        f"Band {res.projected_risk_band.value}</span>",
        unsafe_allow_html=True,
    )

    r3.metric(
        "Projected Monthly Premium",
        f"${res.projected_monthly_premium:.2f}",
        delta=f"-${res.monthly_savings:.2f}" if res.monthly_savings > 0 else f"+${abs(res.monthly_savings):.2f}",
        delta_color="inverse",
    )

    r4.metric(
        "Projected Annual Savings",
        f"${res.annual_savings:,.2f}",
        delta="Annual Discount" if res.annual_savings > 0 else "Surcharge",
    )


if __name__ == "__main__":
    render()
