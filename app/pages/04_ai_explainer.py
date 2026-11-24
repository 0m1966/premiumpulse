"""AI Explainer and Underwriting Guidelines Q&A page with active guardrails."""

import streamlit as st

from app.styles import render_mode_badge
from premiumpulse.ai.chains import AIExplanationService
from premiumpulse.ai.facts import build_quote_facts
from premiumpulse.db.client_factory import get_current_mode
from premiumpulse.services.pricing_service import PricingService


def render():
    col1, col2 = st.columns([3, 1])
    with col1:
        st.title("🤖 Grounded AI Policy Explainer")
        st.caption("Anti-Hallucinating Plain-English Narration & Guideline Assistance")
    with col2:
        render_mode_badge(get_current_mode())

    service = PricingService()
    ai_service = AIExplanationService()

    driver_list = service.list_drivers(limit=100)
    if not driver_list:
        st.warning("No driver records found.")
        return

    driver_options = [f"{d['driver_id']} - {d.get('full_name', 'Unknown')}" for d in driver_list]
    selected_option = st.selectbox("Select Policyholder", driver_options)
    selected_id = selected_option.split(" - ")[0]

    quote = service.get_driver_quote(selected_id)
    score = service.get_driver_score(selected_id)

    # Active Guardrail Indicator Chips
    st.markdown("""
    <div style="display: flex; gap: 8px; margin-bottom: 16px;">
        <span style="background-color: #0E4438; color: #00D2BA; padding: 4px 10px; border-radius: 8px; font-size: 0.8rem; border: 1px solid #00D2BA;">
            🛡️ NumberGrounder: ENFORCED
        </span>
        <span style="background-color: #0E4438; color: #00D2BA; padding: 4px 10px; border-radius: 8px; font-size: 0.8rem; border: 1px solid #00D2BA;">
            🏷️ Citation Verifier: ACTIVE
        </span>
        <span style="background-color: #0E4438; color: #00D2BA; padding: 4px 10px; border-radius: 8px; font-size: 0.8rem; border: 1px solid #00D2BA;">
            🔒 Injection Filter: STRICT
        </span>
    </div>
    """, unsafe_allow_html=True)

    tab_explain, tab_tips, tab_guidelines = st.tabs([
        "📄 Explain My Premium",
        "💡 3 Coaching Tips",
        "📖 Underwriting Guidelines Q&A",
    ])

    with tab_explain:
        if st.button("Generate Grounded Explanation", type="primary"):
            with st.spinner("Extracting verified facts and generating explanation..."):
                res = ai_service.explain_quote(quote, score)

            if res.get("fallback_used"):
                st.warning(f"⚠️ {res.get('notice', 'Standard summary rendered.')}")

            st.markdown(f"### Summary\n{res['summary']}")

            if res.get("top_drivers_of_price"):
                st.markdown("#### Primary Rating Drivers")
                for d in res["top_drivers_of_price"]:
                    st.info(f"**{d['factor_name']}** (Ref: `{d['cited_fact_id']}`): {d['impact_description']}")

            st.caption(f"Citations Verified: `{', '.join(res.get('cited_fact_ids', []))}` | Latency: `{res.get('latency_ms', 0)} ms`")

            # Transparency Expander
            with st.expander("🔍 Inspect Verified Facts Payload (<facts>)"):
                facts_obj = build_quote_facts(quote, score)
                st.json([f.model_dump() for f in facts_obj.facts])

    with tab_tips:
        if st.button("Generate 3 Personalized Tips", type="secondary"):
            with st.spinner("Analyzing driving infractions..."):
                tips_res = ai_service.get_coaching_tips(quote, score)

            st.markdown("### Actionable Driving Tips")
            for idx, tip in enumerate(tips_res.get("tips", []), 1):
                st.success(f"**Tip {idx}: {tip['factor']}**\n\n{tip['advice']}\n*(Ref: `{tip['estimated_points_gain_fact_id']}`)*")

            st.caption(f"Citations: `{', '.join(tips_res.get('cited_fact_ids', []))}`")

    with tab_guidelines:
        st.markdown("Ask any question regarding the certified underwriting and rating manual:")
        user_q = st.text_input(
            "Query Guidelines",
            placeholder="e.g. What is the minimum driving distance required for telematics rating?",
        )
        if st.button("Search & Answer"):
            if user_q:
                with st.spinner("Retrieving clauses and generating answer..."):
                    ans_res = ai_service.ask_guidelines(user_q)
                st.markdown(f"**Answer**: {ans_res['answer']}")
                if ans_res.get("cited_clause_ids"):
                    st.caption(f"Cited Clauses: `{', '.join(ans_res['cited_clause_ids'])}`")
            else:
                st.warning("Please enter a question.")


if __name__ == "__main__":
    render()
