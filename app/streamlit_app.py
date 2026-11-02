"""QueryForge demo app: Ask a data question, see the benchmark. Run: streamlit run app/streamlit_app.py

Display only: answers come from agent.answer() (or the cached demo answers), unchanged.
"""
import json
import re
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
MODEL_NAMES = {
    CFG["models"]["small"]["id"]: "GLM 5.3 Flash",
    CFG["models"]["large"]["id"]: "NVIDIA Nemotron 3 Ultra",
    CFG["models"]["tuned"]["id"]: "GLM 5.3 Flash + QueryForge LoRA",
}
RATE_COL = re.compile(r"(rate|share|ratio|fraction|pct|percent|growth)", re.I)
PCT_COL = re.compile(r"(pct|percent)", re.I)

st.set_page_config(page_title="QueryForge", page_icon="🔎", layout="wide")


def model_label(model_id: str) -> str:
    name = MODEL_NAMES.get(model_id)
    return f"{name} · `{model_id}`" if name else f"`{model_id}`"


def _num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _is_rate(col, values):
    nums = [v for v in values if _num(v)]
    return bool(nums) and bool(RATE_COL.search(col or ""))


def fmt_value(col, v, rate_cols):
    """Rates/shares as % with 1 decimal; other numbers with thousands separators."""
    if not _num(v):
        return v
    if col in rate_cols:
        already_pct = rate_cols[col]
        return f"{v:.1f}%" if already_pct else f"{100 * v:.1f}%"
    if isinstance(v, int) or float(v).is_integer():
        return f"{int(v):,}"
    return f"{v:,.2f}"


def rate_columns(columns, rows):
    """{col: values_already_in_percent} for rate-like columns."""
    out = {}
    for j, c in enumerate(columns or []):
        vals = [r[j] for r in rows]
        if _is_rate(c, vals):
            nums = [v for v in vals if _num(v)]
            out[c] = bool(PCT_COL.search(c)) or any(abs(v) > 1 for v in nums)
    return out


def display_df(resp):
    rc = rate_columns(resp.columns, resp.rows)
    return pd.DataFrame([[fmt_value(c, v, rc) for c, v in zip(resp.columns, r)] for r in resp.rows],
                        columns=resp.columns)


def pretty(col):
    return (col or "value").replace("_", " ")


def answer_sentence(resp) -> str:
    """One plain-English sentence summarising the result (display only)."""
    if resp.action == "clarify":
        return "QueryForge needs one detail before it can answer."
    if resp.action in ("refuse",):
        return "QueryForge can't run this request."
    if resp.action == "escalate" or resp.error:
        return "QueryForge couldn't answer this confidently; it has been sent to a data engineer."
    rows, cols = resp.rows or [], resp.columns or []
    if not rows:
        return "The query ran but returned no rows."
    rc = rate_columns(cols, rows)
    if len(rows) == 1 and len(cols) == 1:
        return f"Answer: **{fmt_value(cols[0], rows[0][0], rc)}** ({pretty(cols[0])})."
    if len(rows) == 1:
        parts = [f"{pretty(c)} **{fmt_value(c, v, rc)}**" for c, v in zip(cols, rows[0])]
        return "Result: " + ", ".join(parts) + "."
    num_j = [j for j in range(len(cols)) if all(_num(r[j]) for r in rows)]
    lab_j = [j for j in range(len(cols)) if j not in num_j]
    if len(cols) == 1:
        items = ", ".join(str(r[0]) for r in rows[:5])
        more = f" and {len(rows) - 5} more" if len(rows) > 5 else ""
        return f"{len(rows)} results: **{items}**{more}."
    if num_j and lab_j:
        j, k = num_j[-1], lab_j[0]
        top = max(rows, key=lambda r: r[j])
        return (f"{len(rows)} rows. Highest {pretty(cols[j])}: **{top[k]}** at "
                f"**{fmt_value(cols[j], top[j], rc)}**.")
    return f"{len(rows)} rows returned."


def render_answer(resp, key: str):
    """Answer card: sentence, metrics, table, explanation, SQL."""
    st.markdown(f"#### {answer_sentence(resp)}")
    m = st.columns(4)
    m[0].metric("Action", resp.action)
    m[1].metric("Confidence", resp.confidence)
    m[2].metric("Latency", f"{resp.latency_ms / 1000:.1f}s")
    m[3].metric("Cost", f"${resp.cost_usd:.5f}")
    st.caption("Model: " + model_label(resp.model_used) + (" (routed to the large model)" if resp.routed else ""))
    if resp.action == "answer" and resp.rows is not None:
        st.dataframe(display_df(resp), width="stretch", hide_index=True)
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


page = st.sidebar.radio("Page", ["Ask", "Benchmark", "Audit log"])

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
        render_answer(resp, tid)
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
