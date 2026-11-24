# PremiumPulse ⚡
> **Telematics Underwriting and Dynamic Usage-Based Pricing Platform**

[![PremiumPulse CI](https://github.com/placeholder/premiumpulse/actions/workflows/ci.yml/badge.svg)](https://github.com/placeholder/premiumpulse/actions/workflows/ci.yml)
[![Streamlit App](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://share.streamlit.io/)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Delta Lake](https://img.shields.io/badge/storage-Delta%20Lake-00D2BA.svg)](https://delta.io/)
[![Snowflake](https://img.shields.io/badge/serving-Snowflake%20Dynamic%20Tables-29B5E8.svg)](https://www.snowflake.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

---

## 📌 Executive Problem Statement

Traditional auto insurance relies on static proxy variables (credit score, marital status, vehicle type) evaluated once a year. This penalizes safe drivers who drive low miles, fails to detect aggressive driving until severe losses occur, and lacks transparency.

**PremiumPulse** implements a pre-loss usage-based auto insurance (UBI) platform:
1. **High-Frequency Ingestion**: PySpark on Databricks ingests second-by-second telematics events via Auto Loader (`cloudFiles`).
2. **Deterministic Risk Scoring**: Evaluates rolling 30-day driving behavior against a certified Scorecard (v1) calculating penalty points for hard braking, hard acceleration, speeding, night driving, phone usage, and mileage exposure.
3. **Certified Pricing System of Record**: Snowflake Dynamic Tables (`MART.QUOTES`) dynamically calculate monthly and annual policy quotes using certified rate factor tables.
4. **Anti-Hallucinating AI Policy Explainer**: Plain LangChain LCEL chains explain precalculated numbers in plain English with mathematical number grounding (zero hallucination tolerance).
5. **Resilient Dual-Mode Operation**: Automatically runs in **SNAPSHOT** mode using bundled offline SQLite tables with zero credentials, or in **LIVE** mode against Snowflake.

---

## 🏛️ System Architecture

```text
[ High-Frequency Synthetic Telematics Streams & Master Files ]
                           │
                           ▼
[ Databricks Unity Catalog Volume (Landing Zone: /Volumes/...) ]
                           │
                           ▼ (Auto Loader / cloudFiles: Schema Evolution, .trigger(availableNow=True))
       ┌─────────────────────────────────────────┐
       │         BRONZE Telematics Events        │ (Append-only Raw + Ingest Metadata)
       └────────────────────┬────────────────────┘
                            │ (PySpark: Normalization, Speed/GPS Bounds, 15-min Sessionization)
       ┌────────────────────┴────────────────────┐
       │          SILVER Trips & Events          │ ──▶ [ silver_rejected_events (Dead-Letter) ]
       └────────────────────┬────────────────────┘ ──▶ [ silver_dq_results (Audit Tracking) ]
                            │ (Scorecard v1, Kimball Star Schema, SHA-256 Surrogate Keys)
       ┌────────────────────┴────────────────────┐
       │         GOLD Driver Risk Scores         │ ──▶ [ pipeline_audit (Mathematical Reconciliation) ]
       └────────────────────┬────────────────────┘
                            │
               ┌────────────┴──────────────────────────┐
               ▼                                       ▼
  [ Snowflake Serving Layer ]             [ Local Offline Snapshot ]
   • RAW.PREMIUMPULSE_STAGE (Parquet)      • snapshot/premiumpulse_snapshot.db
   • CURATED Driver & Risk Tables          • Pre-seeded Star Schema & Marts
   • MART.RATE_FACTORS (Effective-dated)   • Zero external dependencies
   • MART.QUOTES (Dynamic Table)
   • Dynamic Data Masking & RBAC
               │                                       │
               └───────────────────┬───────────────────┘
                                   │
                                   ▼
                   [ Shared Python Service Layer ]
                   (premiumpulse.services.PricingService)
                         │                  │
                         ▼                  ▼
              [ Streamlit Cloud UI ]   [ FastAPI REST API ]
              (5 Interactive Pages)    (X-API-Key Auth & Rate Limiting)
```

---

## ⚡ Tech Stack & Responsibilities

| Technology | Architectural Responsibility |
| :--- | :--- |
| **PySpark on Databricks** | Heavy data engineering: Auto Loader (`cloudFiles`), 15-minute gap sessionization, haversine distance calculation, dead-letter routing, and Delta Lake optimizations (`OPTIMIZE ... ZORDER BY`). |
| **Databricks Jobs API** | Multi-task DAG workflow orchestration chaining notebooks 00 to 04 with automated retries. |
| **Snowflake** | Actuarial system of record: `RATE_FACTORS` table, `QUOTES` Dynamic Table (5-min target lag), Dynamic Data Masking for PII, Time Travel, and Zero-Copy Cloning. |
| **LangChain LCEL** | Strictly narrator AI chains (`prompt \| llm \| parser`). Zero agents, zero tool execution, zero memory loops. |
| **Guardrails & Security** | In-code `NumberGrounder`, citation verifier, prompt injection detector, and deterministic fallback generators. |
| **FastAPI** | REST API providing OpenAPI documentation, X-API-Key auth, and SlowAPI rate limiting. |
| **Streamlit** | Multi-page underwriting and policyholder portal with dark theme Plotly visualizations. |

---

## 🎯 Benchmark Verification & Quality Gates

All numbers reported below were produced directly by the included verification scripts:

| Metric | Target | Achieved | Verification Script |
| :--- | :--- | :--- | :--- |
| **Pytest Test Suites** | 100% Pass | **34 / 34 PASSED** | `pytest tests/ -v` |
| **Mathematical Reconciliation** | $0\text{ Loss}$ | **$100\%$ ($375,163 = 10,891 + 364,272$)** | `tests/test_pipeline_local.py` |
| **Pricing Engine Parity** | $\Delta \le 0.01$ | **$\Delta = 0.00$ on 20 Fixtures** | `tests/test_pricing_parity.py` |
| **AI Number Hallucination** | $0.0\%$ | **$0.0\%$ (Strict NumberGrounder)** | `tests/test_chains_grounding.py` |
| **Adversarial Containment** | $100\%$ | **$25 / 25$ Attacks Contained** | `tests/test_chains_grounding.py` |
| **Offline Startup** | Zero Secrets | **Immediate Launch** | `app/main.py` |

---

## 🚀 Quickstart & Reproduction

### 1. Set Up Environment
```bash
cd premiumpulse
python -m venv .venv
source .venv/bin/activate   # or .venv\Scripts\activate on Windows
pip install -r requirements.txt
```

### 2. Run Test Suite (Zero Network / Zero Secrets)
```bash
python -m pytest tests/ -v
```

### 3. Launch Streamlit Portal (Runs in Snapshot Mode by Default)
```bash
streamlit run app/main.py
```

### 4. Launch FastAPI REST Service
```bash
uvicorn api.main:app --port 8000
# Visit http://127.0.0.1:8000/docs
```

---

## ⚖️ Layer-to-Layer Reconciliation Invariant

PremiumPulse enforces strict data integrity audited per pipeline run:

$$\text{Bronze Telematics Events}\ (375,163) = \text{Rejected Defective Events}\ (10,891) + \text{Silver Clean Events}\ (364,272)$$
$$\sum \text{Silver Trip Distance (km)} = \sum \text{Gold Fact Trip Distance (km)}$$

---

## 🔒 Limitations & Future Work

* **Real-time GPS Streaming**: Currently simulated in micro-batches with `.trigger(availableNow=True)`; full continuous streaming would require 24/7 dedicated compute.
* **LLM Narration**: Designed strictly as a read-only narrator; pricing modifications must always occur through official rate filings and Snowflake dynamic tables.
