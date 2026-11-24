"""Pipeline Lineage, Data Quality Guardrails & Reconciliation Audit page."""

import sqlite3
import pandas as pd
import streamlit as st

from app.styles import render_mode_badge
from premiumpulse.db.client_factory import get_current_mode, get_db_client


def render():
    col1, col2 = st.columns([3, 1])
    with col1:
        st.title("⚙️ Data Pipeline & Quality Guardrails")
        st.caption("Databricks Medallion Architecture, Reconciliation Audit & Snowflake Marts")
    with col2:
        render_mode_badge(get_current_mode())

    db = get_db_client()

    # System Architecture Diagram
    st.subheader("1. Medallion Lakehouse Architecture")
    st.code("""
    [ Raw Telematics Event Batches + Schema Drift ]
                         │
                         ▼
    [ Databricks Unity Catalog Volume (Landing Zone) ]
                         │
                         ▼ (Auto Loader: cloudFiles, schemaEvolutionMode=addNewColumns)
        ┌────────────────────────────────────┐
        │       BRONZE Telematics Events     │ (Append-only Raw + Ingest Metadata)
        └─────────────────┬──────────────────┘
                          │ (PySpark: Deduplication, Speed/GPS Validation, 15-min Sessionization)
        ┌─────────────────┴──────────────────┐
        │        SILVER Trips & Events       │ ──▶ [ silver_rejected_events (Dead-Letter) ]
        └─────────────────┬──────────────────┘ ──▶ [ silver_dq_results (Audit Tracking) ]
                          │ (Scorecard v1, Kimball Star Schema, SHA-256 Surrogate Keys)
        ┌─────────────────┴──────────────────┐
        │       GOLD Driver Risk Scores      │ ──▶ [ pipeline_audit (Mathematical Reconciliation) ]
        └─────────────────┬──────────────────┘
                          │
                          ▼
            [ Snowflake Serving Layer ]
             • Curated Dimensions & Risk Scores
             • MART.RATE_FACTORS (Effective-dated)
             • MART.QUOTES (Dynamic Table with 5-min target lag)
             • Dynamic Data Masking & RBAC
    """, language="text")

    st.divider()

    # Mathematical Zero-Loss Reconciliation Invariant
    st.subheader("2. Mathematical Zero-Loss Reconciliation Audit")
    audit_rows = db.execute_query("SELECT * FROM pipeline_audit ORDER BY audit_ts DESC LIMIT 1;")
    if audit_rows:
        audit = audit_rows[0]
        st.markdown(f"""
        $$\\text{{Bronze Events}} ({audit['bronze_event_count']:,}) = \\text{{Rejected Events}} ({audit['rejected_event_count']:,}) + \\text{{Silver Clean Events}} ({audit['silver_clean_event_count']:,})$$
        """)
        st.success(f"Mathematical Reconciliation Invariant Status: **{audit['reconciliation_status']}** (Audited: `{audit['audit_ts']}`)")

    st.divider()

    # Data Quality Rules Audit Table
    st.subheader("3. Silver Data Quality Results (Automated Guardrails)")
    dq_rows = db.execute_query("SELECT * FROM silver_dq_results;")
    if dq_rows:
        st.dataframe(pd.DataFrame(dq_rows), use_container_width=True, hide_index=True)

    st.divider()

    # Rejected Events Dead-Letter Sample
    st.subheader("4. Rejected Sensor Events Sample (Dead-Letter Queue)")
    rej_rows = db.execute_query("SELECT event_id, driver_id, event_ts, reject_reason FROM silver_rejected_events LIMIT 10;")
    if rej_rows:
        st.dataframe(pd.DataFrame(rej_rows), use_container_width=True, hide_index=True)


if __name__ == "__main__":
    render()
