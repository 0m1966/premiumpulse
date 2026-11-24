"""PremiumPulse: Streamlit Portal Entry Point.

Telematics Underwriting and Dynamic Pricing Platform.
"""

import streamlit as st
from premiumpulse.db.client_factory import get_current_mode
from app.styles import render_mode_badge, THEME_PRIMARY

st.set_page_config(
    page_title="PremiumPulse | Telematics Underwriting",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Header & Mode Badge
col_title, col_badge = st.columns([3, 1])
with col_title:
    st.title("⚡ PremiumPulse")
    st.caption("Enterprise Telematics Underwriting & Usage-Based Dynamic Pricing Platform")

with col_badge:
    current_mode = get_current_mode()
    render_mode_badge(current_mode)

st.markdown("---")

# Executive Introduction
st.markdown("""
### 🛡️ Pre-Loss Telematics Risk Scoring & Actuarial Rating
**PremiumPulse** bridges high-frequency connected vehicle telematics with real-time actuarial pricing.

* **Databricks Medallion Lakehouse**: PySpark Auto Loader (`cloudFiles`) ingests second-by-second telematics streams, cleans sensor anomalies, sessionizes driving trips, and builds Kimball Gold Star Schema models.
* **Snowflake Serving Mart**: Snowflake dynamic tables (`MART.QUOTES`) execute certified multiplicative rate formulas joining risk scores with effective-dated rate factor tables.
* **Anti-Hallucinating AI Explainer**: Plain LangChain LCEL chains translate precalculated numeric facts into transparent policyholder summaries with deterministic number grounding.
* **Resilient Dual-Mode Operation**: Seamlessly runs in **LIVE** mode when connected to cloud warehouses, or in zero-credential **SNAPSHOT** mode using bundled Parquet/SQLite tables.
""")

st.divider()

# Navigation Cards
st.markdown("### 🧭 Platform Navigation")
c1, c2, c3 = st.columns(3)
with c1:
    st.info("**📊 Portfolio Overview**\n\nExamine portfolio-level driver risk distributions, premium yields, and vehicle segmentations.")
    st.markdown("[Go to Portfolio Overview](01_portfolio)")

with c2:
    st.info("**👤 Driver Profiles**\n\nDeep-dive into individual driver scores, risk factor penalties, and rate multiplier breakdowns.")
    st.markdown("[Go to Driver Profile](02_driver_profile)")

with c3:
    st.info("**🎛️ What-If Simulator**\n\nSimulate telematics behavior improvements to project score gains and policy premium discounts.")
    st.markdown("[Go to Quote Simulator](03_quote_simulator)")

c4, c5 = st.columns(2)
with c4:
    st.info("**🤖 Grounded AI Explainer**\n\nRead plain-English quote explanations backed by strict NumberGrounder citation verification.")
    st.markdown("[Go to AI Explainer](04_ai_explainer)")

with c5:
    st.info("**⚙️ Data Pipeline & Quality**\n\nInspect Medallion lineage, Auto Loader schema evolution, and zero-loss reconciliation invariants.")
    st.markdown("[Go to Pipeline & DQ](05_pipeline_and_data_quality)")
