"""QueryForge demo app: Ask a data question, see the benchmark. Run: streamlit run app/streamlit_app.py"""
import json
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from agent.agent import CFG, answer  # noqa: E402
from app import audit_log  # noqa: E402
from contracts import AgentResponse  # noqa: E402

CACHE = ROOT / "app" / "demo_cache.json"  # cached demo answers so the video doesn't depend on wifi
SETUP_NAMES = {"S1": "Baseline (S1)", "S4": "QueryForge harness (S4)", "S5H": "QueryForge fine-tuned + harness (S5H)",
               "S6": "QueryForge router (S6)", "S2": "Nemotron Ultra (S2)"}

st.set_page_config(page_title="QueryForge", page_icon="🔎", layout="wide")
page = st.sidebar.radio("Page", ["Ask", "Benchmark", "Audit log"])


def cached_or_live(q, setup, use_cache):
    cache = json.loads(CACHE.read_text()) if CACHE.exists() else {}
    key = f"{setup}::{q.strip().lower()}"
    if use_cache and key in cache:
        return AgentResponse(**cache[key])
    resp = answer(q, setup)
    if not resp.error:
        cache[key] = resp.model_dump()
        CACHE.write_text(json.dumps(cache, indent=1, default=str))
    return resp


if page == "Ask":
    st.title("QueryForge")
    st.caption("Ask a data question in plain English. Answers come from the Olist database (as of 2018-08-31), read-only.")
    c1, c2, c3 = st.columns([2, 1, 1])
    requester = c1.text_input("Requester", "kam@company.com")
    role = c2.selectbox("Role", ["analyst", "pm", "auditor", "ops"])
    available = [s for s in SETUP_NAMES if s in CFG["setups"] and (s not in ("S5", "S5H") or CFG["models"]["tuned"]["id"])]
    setup = c3.selectbox("Setup", available, index=available.index("S4") if "S4" in available else 0,
                         format_func=SETUP_NAMES.get)
    q = st.text_area("Ticket", "whats the late delivery rate by customer region for last month", height=90)
    use_cache = st.toggle("Use cached demo answers", value=True)
    if st.button("Submit ticket", type="primary") and q.strip():
        with st.spinner("Writing and running SQL..."):
            resp = cached_or_live(q, setup, use_cache)
        st.session_state["last"] = (audit_log.log_ticket(resp, q, setup, requester, role), resp)

    if "last" in st.session_state:
        tid, resp = st.session_state["last"]
        m = st.columns(5)
        m[0].metric("Action", resp.action)
        m[1].metric("Confidence", resp.confidence)
        m[2].metric("Latency", f"{resp.latency_ms / 1000:.1f}s")
        m[3].metric("Cost", f"${resp.cost_usd:.5f}")
        m[4].metric("Model", resp.model_used.split("/")[-1][:22] + (" (routed)" if resp.routed else ""))
        if resp.action == "answer" and resp.rows is not None:
            st.dataframe(pd.DataFrame(resp.rows, columns=resp.columns), width="stretch")
        if resp.clarifying_question:
            st.info(f"**Clarifying question:** {resp.clarifying_question}")
        if resp.refusal_reason:
            st.warning(f"**Refused:** {resp.refusal_reason}")
        if resp.error:
            st.error(resp.error)
        if resp.explanation:
            st.write(f"**Explanation:** {resp.explanation}")
        if resp.assumptions:
            st.write("**Assumptions:**\n" + "\n".join(f"- {a}" for a in resp.assumptions))
        if resp.sql:
            with st.expander("SQL"):
                st.code(resp.sql, language="sql")
        a, b = st.columns(2)
        if a.button("Approve"):
            audit_log.set_status(tid, "approved", requester)
            st.success("Approved and logged.")
        if b.button("Flag for data engineer"):
            audit_log.set_status(tid, "flagged", requester)
            st.warning("Flagged for review.")

elif page == "Benchmark":
    st.title("Benchmark")
    md = ROOT / "eval" / "results.md"
    if md.exists():
        st.markdown(md.read_text())
    for name in ["ladder", "significance", "intervals", "tradeoff", "seen_unseen"]:
        p = ROOT / "eval" / "figures" / f"{name}.png"
        if p.exists():
            st.image(str(p), width="stretch")

else:
    st.title("Audit log")
    rows = audit_log.recent()
    if rows:
        df = pd.DataFrame(rows)
        f = st.text_input("Search")
        if f:
            df = df[df.apply(lambda r: f.lower() in " ".join(map(str, r.values)).lower(), axis=1)]
        st.dataframe(df, width="stretch")
    else:
        st.write("No tickets yet.")
