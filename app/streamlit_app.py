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
# Model name first, setup code as a tag (codes match eval/runs/ and config.yaml).
SETUP_NAMES = {"S1": "Baseline · GLM 5.3 Flash (S1)", "S4": "QueryForge · GLM 5.3 Flash + harness (S4)",
               "S5H": "QueryForge · GLM 5.3 Flash fine-tuned + harness (S5H)",
               "S6": "QueryForge · GLM 5.3 Flash + harness → Nemotron 3 Ultra (S6)",
               "S2": "Nemotron 3 Ultra (S2)"}
ALL_SETUP_NAMES = {"S0": "GLM 5.3 Flash, schema only (S0)", "S5": "GLM 5.3 Flash fine-tuned (S5)", **SETUP_NAMES}
# Compact model-only labels for narrow table columns
MODEL_ONLY = {"S0": "GLM 5.3 Flash, schema only", "S1": "GLM 5.3 Flash", "S2": "Nemotron 3 Ultra",
              "S4": "GLM 5.3 Flash + harness", "S5": "GLM 5.3 Flash fine-tuned", "S5H": "GLM 5.3 Flash FT + harness",
              "S6": "GLM 5.3 Flash → Nemotron 3 Ultra"}
MODEL_NAMES = {
    CFG["models"]["small"]["id"]: "GLM 5.3 Flash",
    CFG["models"]["large"]["id"]: "NVIDIA Nemotron 3 Ultra",
    CFG["models"]["tuned"]["id"]: "GLM 5.3 Flash + QueryForge LoRA",
}
# One-click example tickets; every one has cached answers for S1 and S4 in app/demo_cache.json.
EXAMPLES = [
    ("Business rule", "whats the late delivery rate by customer region for last month"),
    ("Trap", "how are orders from são paulo-based sellers rated on average"),
    ("Clarify", "how are sellers in the south doing"),
    ("Refuse", "delete the canceled orders"),
    ("Multi-step", "which seller state had the worst late rate in 2017? only states w 100+ delivered orders pls"),
]
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
        return "Needs one detail before answering."
    if resp.action in ("refuse",):
        return "This request can't be run."
    if resp.action == "escalate" or resp.error:
        return "No answer: the query failed, so this goes to a data engineer."
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


# (label, pattern searched in the SQL) for the "Rules applied" chips. Display only.
SQL_RULES = [
    ("Valid order rule", r"not in \(\s*'canceled'\s*,\s*'unavailable'\s*\)"),
    ("GMV = item price", r"sum\(\s*(\w+\.)?price\s*\)"),
    ("Freight revenue", r"sum\(\s*(\w+\.)?freight_value\s*\)"),
    ("Paid amount", r"payment_value"),
    ("Customer = customer_unique_id", r"customer_unique_id"),
    ("Late delivery rule", r"order_delivered_customer_date.{0,40}>\s*.{0,25}order_estimated_delivery_date"),
    ("Delivery time rule", r"date_diff\(\s*'day'"),
    ("Active seller (90 days)", r"2018-06-02"),
    ("Low rating (score ≤ 2)", r"review_score\s*(<=\s*2|<\s*3)"),
    ("Customer region", r"customer_state.{0,80}regions|regions.{0,80}customer_state"),
    ("Seller region", r"seller_state.{0,80}regions|regions.{0,80}seller_state"),
    ("English category name", r"category_en"),
    ("Distinct orders", r"count\(\s*distinct\s+(\w+\.)?order_id\s*\)"),
    ("Reviews not double-counted", r"order_id\s+in\s*\(\s*select"),
    ("Period by purchase date", r"order_purchase_timestamp\s*(>=|<|between)"),
    ("Period by review date", r"review_creation_date\s*(>=|<|between)"),
]
RELATIVE_Q = re.compile(r"\b(last|this|past)\s+(month|quarter|year|\d+\s+days)|\b(rn|right now|currently|today|recent)\b", re.I)


def rules_applied(question: str, resp) -> list[str]:
    """Short labels for the business rules and assumptions an answer used (derived for display)."""
    if resp.action == "refuse":
        reason = (resp.refusal_reason or "").lower()
        labels = []
        if re.search(r"read|write|delet|modif|drop|insert|updat|chang|creat|truncat|select", reason):
            labels.append("Read-only: no writes")
        if re.search(r"personal|name|phone|email|address|contact|cpf|card", reason):
            labels.append("No personal data")
        if re.search(r"instruction|injection|command", reason):
            labels.append("Injection blocked")
        return labels or ["Out of scope"]
    if resp.action == "clarify":
        return ["Ambiguous term not defined in the dictionary"]
    if resp.error or resp.rows is None:
        return []
    sql = re.sub(r"\s+", " ", (resp.sql or "").lower())
    labels = [label for label, pat in SQL_RULES if re.search(pat, sql)]
    if "seller_state" in sql and "Seller region" not in labels:
        labels.append("Seller location (seller_state)")
    text = " ".join(resp.assumptions or []).lower() + " " + (question or "").lower()
    if RELATIVE_Q.search(question or "") or "2018-08-31" in text or "as-of" in text:
        labels.append("As-of date 2018-08-31")
    if re.search(r"\bfiscal\b|\bfy\s?\d", text):
        labels.append("Fiscal year starts Feb 1")
    if "%" in (question or "") or "percent" in text:
        labels.append("Shown as % (asked for)")
    return labels


def render_chips(labels):
    if labels:
        st.markdown("**Rules applied** &nbsp;" + " ".join(f":blue-badge[{lab}]" for lab in labels))


def render_answer(resp, key: str, compact: bool = False, question: str = ""):
    """Answer card: sentence, metrics, table, explanation, SQL."""
    st.markdown(f"#### {answer_sentence(resp)}")
    metrics = [("Confidence", resp.confidence), ("Latency", f"{resp.latency_ms / 1000:.1f}s"),
               ("Cost", f"${resp.cost_usd:.5f}"), ("Action", "failed" if resp.error else resp.action)]
    rows = [metrics[:2], metrics[2:]] if compact else [metrics]
    for row in rows:
        for col, (label, value) in zip(st.columns(len(row)), row):
            col.metric(label, value)
    st.caption("Model: " + model_label(resp.model_used) + (" (routed to the large model)" if resp.routed else ""))
    if resp.action == "answer" and resp.rows is not None:
        st.dataframe(display_df(resp), width="stretch", hide_index=True)
    if resp.clarifying_question:
        st.info(f"**Clarifying question:** {resp.clarifying_question}")
    if resp.refusal_reason:
        st.warning(f"**Refused:** {resp.refusal_reason}")
    if resp.error:
        st.error(resp.error)
    render_chips(rules_applied(question, resp))
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


CSS = """
<style>
.stApp { background: linear-gradient(180deg, #f5f7fb 0%, #eef2fb 100%); }
.block-container { padding-top: 3.6rem; max-width: 1280px; }
[data-testid="stHeader"] { background: transparent; }
h1 { background: linear-gradient(90deg, #4338ca, #0d9488); -webkit-background-clip: text; background-clip: text;
     color: transparent !important; font-weight: 800 !important; letter-spacing: -0.02em; }
[data-testid="stSidebar"] { background: linear-gradient(180deg, #1e1b4b 0%, #312e81 55%, #115e59 100%);
     min-width: 240px !important; max-width: 240px !important; }
[data-testid="stSidebar"] * { color: #eef2ff !important; }
[data-testid="stMetric"] { background: #ffffff; border: 1px solid #e3e8f4; border-radius: 14px;
     padding: 0.8rem 1rem; box-shadow: 0 1px 3px rgba(30, 27, 75, 0.06); }
[data-testid="stExpander"] { background: #ffffff; border-radius: 12px; }
.qf-hero { background: linear-gradient(120deg, #1e1b4b 0%, #4338ca 45%, #0d9488 100%); border-radius: 20px;
     padding: 2.1rem 2.4rem; color: #ffffff; box-shadow: 0 10px 30px rgba(67, 56, 202, 0.25); margin-bottom: 1.2rem; }
.qf-hero .qf-name { font-size: 3rem; font-weight: 800; letter-spacing: -0.03em; line-height: 1.05;
     background: linear-gradient(90deg, #ffffff, #a5f3fc); -webkit-background-clip: text; background-clip: text;
     color: transparent; }
.qf-hero .qf-tag { font-size: 1.2rem; margin-top: 0.4rem; color: #e0e7ff; }
.qf-hero .qf-pills { margin-top: 1rem; }
.qf-hero .qf-pill { display: inline-block; background: rgba(255, 255, 255, 0.14); border: 1px solid rgba(255, 255, 255, 0.28);
     border-radius: 999px; padding: 0.2rem 0.75rem; margin: 0 0.4rem 0.4rem 0; font-size: 0.85rem; color: #ffffff; }
.qf-cards { display: grid; grid-template-columns: repeat(3, 1fr); gap: 1rem; margin-bottom: 1.4rem; }
@media (max-width: 900px) { .qf-cards { grid-template-columns: 1fr; } }
.qf-card { background: #ffffff; border-radius: 16px; padding: 1.1rem 1.3rem; border: 1px solid #e3e8f4;
     box-shadow: 0 2px 10px rgba(30, 27, 75, 0.06); border-top: 5px solid var(--accent); }
.qf-card h4 { margin: 0 0 0.4rem 0; color: var(--accent); font-size: 1.05rem; }
.qf-card p { margin: 0; color: #374151; font-size: 0.95rem; line-height: 1.5; }
.qf-card b { color: #111827; }
.qf-brand { font-size: 1.6rem; font-weight: 800; letter-spacing: -0.02em; margin-bottom: 0.1rem; }
.qf-brand-sub { font-size: 0.85rem; opacity: 0.85; margin-bottom: 1rem; }
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)
st.sidebar.markdown('<div class="qf-brand">🔎 QueryForge</div>'
                    '<div class="qf-brand-sub">Data tickets, answered in seconds</div>', unsafe_allow_html=True)


def proof_numbers():
    """Headline numbers for the hero cards, read from eval/summary.json so they match the benchmark."""
    p = ROOT / "eval" / "summary.json"
    if not p.exists():
        return None
    s = json.loads(p.read_text())
    v, u = s["stats_vs_S1"]["S4"]["answer_combined"], s["stats_vs_S1"]["S4_vs_S2"]["answer_combined"]
    cost = {k: s["summaries"][k]["combined"]["cost_per_1k"] for k in ("S4", "S2")}
    gap = lambda x: round(round(100 * x["new_acc"], 1) - round(100 * x["base_acc"], 1), 1)  # noqa: E731
    return {"base": 100 * v["base_acc"], "new": 100 * v["new_acc"], "p": v["p_value"], "n": v["n"],
            "vs_ultra": gap(u), "cost_ratio": cost["S2"] / cost["S4"]}


def hero():
    st.markdown(
        '<div class="qf-hero"><div class="qf-name">QueryForge</div>'
        '<div class="qf-tag">Ask a data question like a ticket. Get the answer, the SQL and the business rules '
        'behind it in seconds, not days.</div><div class="qf-pills">'
        '<span class="qf-pill">GLM 5.3 Flash on Fireworks</span><span class="qf-pill">Read-only SQL</span>'
        '<span class="qf-pill">Business rules built in</span><span class="qf-pill">Audit trail</span></div></div>',
        unsafe_allow_html=True)
    pn = proof_numbers()
    proof = (f"On a frozen benchmark of {pn['n']} answerable questions, accuracy goes from <b>{pn['base']:.1f}% to "
             f"{pn['new']:.1f}%</b> over the same model alone (p = {pn['p']:.4f}). It also beats NVIDIA Nemotron 3 Ultra "
             f"by <b>{pn['vs_ultra']:+.1f} pts</b> at about <b>1/{pn['cost_ratio']:.0f} of the cost</b>."
             if pn else "See the Benchmark page.")
    st.markdown(
        '<div class="qf-cards">'
        '<div class="qf-card" style="--accent:#e76f51"><h4>The problem</h4><p>PMs, auditors and ops teams need '
        'numbers but can\'t write SQL. Their tickets wait <b>hours or days</b> for a data engineer. Generic AI tools '
        'don\'t know company definitions: is "revenue" with or without canceled orders? Who counts as a '
        '"customer"? So they get exactly those questions wrong.</p></div>'
        '<div class="qf-card" style="--accent:#4338ca"><h4>What QueryForge does</h4><p>It reads the schema and the '
        'company\'s <b>business rules</b>, writes one SQL query, runs it <b>read-only</b>, checks the result and '
        'answers with the SQL and its assumptions. If a ticket is ambiguous it <b>asks</b>. If it asks to change '
        'data or for personal data it <b>refuses</b>. Every answer is logged for review.</p></div>'
        f'<div class="qf-card" style="--accent:#0d9488"><h4>The proof</h4><p>{proof}</p></div>'
        '</div>', unsafe_allow_html=True)


page = st.sidebar.radio("Page", ["Ask", "Benchmark", "Audit log"])

if page == "Ask":
    hero()
    with st.expander("How it works"):
        st.markdown(
            "1. **Pre-filter:** requests to change or delete data, requests for personal data, prompt injection and "
            "non-data questions are refused before any model call.\n"
            "2. **Context:** the model, GLM 5.3 Flash on Fireworks, gets the schema, the company's **business "
            "rules** (valid order, GMV, active seller, late delivery, fiscal year, as-of date…) and the real values of "
            "key columns (statuses, states, category names).\n"
            "3. **SQL:** the model returns one SELECT query, or asks a clarifying question if the ticket is ambiguous.\n"
            "4. **Safety:** the query is parsed, must be a single read-only SELECT, and can only use known tables. It "
            "runs on a read-only connection with a 10-second timeout.\n"
            "5. **Retry and checks:** if the query fails, the error goes back to the model (up to 2 retries). Sanity "
            "checks catch empty results, rates outside 0–1 and too many rows, and the model gets one chance to repair.\n"
            "6. **Answer:** a plain-English answer, the table, the SQL, the rules applied and a confidence level. Every "
            "ticket is written to the audit log, where a reviewer can approve or flag it.\n\n"
            "**Baseline vs QueryForge:** both use GLM 5.3 Flash with the same prompt and business rules. The baseline "
            "is a single model call. QueryForge adds steps 1, 2 (column values), 5 and the review flow. On the frozen "
            "benchmark that lifts accuracy from 90.7% to 94.9% (p = 0.0015). See the Benchmark page.")
    c1, c2, c3 = st.columns([2, 1, 1])
    requester = c1.text_input("Requester", "kam@company.com")
    role = c2.selectbox("Role", ["analyst", "pm", "auditor", "ops"])
    available = [s for s in SETUP_NAMES if s in CFG["setups"] and (s not in ("S5", "S5H") or CFG["models"]["tuned"]["id"])]
    setup = c3.selectbox("Setup", available, index=available.index("S4") if "S4" in available else 0,
                         format_func=SETUP_NAMES.get)
    st.markdown("**Try an example ticket**")

    def use_example(question):
        st.session_state["ticket"] = question
        st.session_state["auto_submit"] = True

    for col, (label, question) in zip(st.columns(len(EXAMPLES)), EXAMPLES):
        col.button(label, key=f"ex_{label}", on_click=use_example, args=(question,), width="stretch", help=question)

    st.session_state.setdefault("ticket", "how many watches gifts products are in the catalog")
    q = st.text_area("Ticket", height=90, key="ticket")
    t1, t2 = st.columns(2)
    compare_mode = t1.toggle("Compare Baseline (GLM 5.3 Flash) vs QueryForge (GLM 5.3 Flash + harness)",
                             value=True, key="compare")
    use_cache = t2.toggle("Use cached demo answers", value=True)
    example_click = st.session_state.pop("auto_submit", False)
    if (st.button("Submit ticket", type="primary") or example_click) and q.strip():
        cache_only = use_cache or example_click
        with st.spinner("Writing and running SQL..."):
            if compare_mode:
                # One audit row per ticket: the QueryForge (S4) answer, with the S1 result stored on it.
                base, main = cached_or_live(q, "S1", cache_only), cached_or_live(q, "S4", cache_only)
                tid = audit_log.log_ticket(main, q, "S4", requester, role,
                                           comparison=audit_log.summarize_comparison("S1", base))
                results = [("S1", None, base), ("S4", tid, main)]
            else:
                resp = cached_or_live(q, setup, cache_only)
                results = [(setup, audit_log.log_ticket(resp, q, setup, requester, role), resp)]
        st.session_state["results"] = results
        st.session_state["asked"] = q

    def review_controls(tid, resp):
        """Approve / Flag for answers; refusals and clarifications get their status automatically."""
        status = audit_log.AUTO_STATUS.get(resp.action)
        if status:
            st.caption(f"Logged as **{status}**.")
            return
        a, b = st.columns(2)
        if a.button("Approve", key=f"approve_{tid}"):
            audit_log.set_status(tid, "approved", requester)
            st.success("Approved and logged.")
        if b.button("Flag for data engineer", key=f"flag_{tid}"):
            audit_log.set_status(tid, "flagged", requester)
            st.warning("Flagged for review.")

    results = st.session_state.get("results", [])
    if len(results) > 1:
        for col, (s, tid, resp) in zip(st.columns(len(results), gap="large"), results):
            with col:
                st.subheader(SETUP_NAMES[s])
                render_answer(resp, s, compact=True, question=st.session_state.get("asked", ""))
                if tid:
                    review_controls(tid, resp)
                else:
                    st.caption("Comparison only: stored on the QueryForge ticket in the audit log.")
    elif results:
        s, tid, resp = results[0]
        st.subheader(SETUP_NAMES[s])
        render_answer(resp, s, question=st.session_state.get("asked", ""))
        review_controls(tid, resp)

elif page == "Benchmark":
    st.title("Benchmark")
    st.caption("Frozen test set (416 items) + 30 hand-written questions. Paired comparisons on the same items; "
               "McNemar p and 95% cluster-bootstrap intervals from eval/stats.py.")
    summary_path = ROOT / "eval" / "summary.json"
    summary = json.loads(summary_path.read_text()) if summary_path.exists() else None
    if summary:
        stats, summ = summary["stats_vs_S1"], summary["summaries"]
        s4 = stats["S4"]["answer_combined"]
        s4_s2 = stats["S4_vs_S2"]["answer_combined"]
        cost = {s: summ[s]["combined"]["cost_per_1k"] for s in ("S1", "S4", "S2")}
        # Business math from the README: 200 tickets/month x 90% resolved x 25 min saved x $54.13/h (BLS 2024)
        tickets, resolved, minutes_saved, wage = 200, 0.9, 30 - 5, 54.13
        savings = tickets * resolved * minutes_saved / 60 * wage
        c = st.columns(4)
        # Gaps shown as the difference of the displayed 1-decimal accuracies (same rule as eval/report.py)
        def gap_pts(v):
            return round(round(100 * v["new_acc"], 1) - round(100 * v["base_acc"], 1), 1)

        # "\$" keeps Streamlit from reading a pair of dollar signs as LaTeX
        c[0].metric("QueryForge accuracy", f"{100 * s4['new_acc']:.1f}%",
                    f"{gap_pts(s4):+.1f} pts vs {100 * s4['base_acc']:.1f}% · p = {s4['p_value']:.4f}")
        c[1].metric(f"vs Nemotron 3 Ultra ({100 * s4_s2['base_acc']:.1f}%)", f"{gap_pts(s4_s2):+.1f} pts",
                    "p < 0.001" if s4_s2["p_value"] < 0.001 else f"p = {s4_s2['p_value']:.3f}")
        c[2].metric("Cost per 1k tickets", f"\\${cost['S4']:.2f}",
                    f"baseline \\${cost['S1']:.2f} · Ultra \\${cost['S2']:.2f}", delta_color="off", delta_arrow="off")
        c[3].metric("Est. monthly savings", f"~\\${round(savings, -1):,.0f}", "engineer time, 200 tickets/mo",
                    delta_color="off", delta_arrow="off",
                    help=f"{tickets} tickets × {int(resolved * 100)}% resolved × {minutes_saved} min saved × "
                         f"\\${wage}/h (BLS 2024 median, data scientists)")
        st.caption(f"Accuracy on {s4['n']} answer items (test + hand-written), 95% CI for the S4 gain "
                   f"[{100 * s4['ci95'][0]:+.1f}, {100 * s4['ci95'][1]:+.1f}] pts. Savings are an estimate from stated "
                   "assumptions (see README), not a measurement.")
        st.divider()

    for name, title in [("ladder", "Accuracy by setup"), ("significance", "Disagreements with the baseline"),
                        ("intervals", "Gap vs baseline with 95% interval"), ("tradeoff", "Quality vs cost"),
                        ("seen_unseen", "Seen vs held-out templates vs hand-written")]:
        p = ROOT / "eval" / "figures" / f"{name}.png"
        if p.exists():
            st.subheader(title)
            st.image(str(p), width="stretch")

    if summary:
        st.divider()
        st.subheader("Hand-written questions (n = 30)")
        st.caption("Paired against the baseline (GLM 5.3 Flash, S1) on the same 30 questions. "
                   "n = 30 is small: treat these as directional.")
        hw_rows = []
        for s in ["S0", "S1", "S2", "S4", "S5", "S5H", "S6"]:
            hw = summ.get(s, {}).get("handwritten")
            if not hw:
                continue
            v = stats.get(s, {}).get("answer_handwritten") if s != "S1" else None
            hw_rows.append({
                "Setup": ALL_SETUP_NAMES[s],
                "Accuracy": f"{100 * hw['exec_accuracy']:.1f}%",
                "Only this setup right / only S1 right": "baseline" if s == "S1" else
                f"{v['only_new_right']} / {v['only_base_right']}",
                "McNemar p": "-" if s == "S1" else f"{v['p_value']:.3f}",
                "Verdict": "baseline" if s == "S1" else v["verdict"],
            })
        st.dataframe(pd.DataFrame(hw_rows), width="stretch", hide_index=True)
        with st.expander("Full results tables"):
            md = ROOT / "eval" / "results.md"
            if md.exists():
                st.markdown(md.read_text())

else:
    st.title("Audit log")
    st.caption("One row per submitted ticket: who asked, what QueryForge did, and whether a reviewer approved or flagged it.")
    all_rows = audit_log.recent()
    counts = {s: sum(r["status"] == s for r in all_rows) for s in audit_log.STATUSES}
    cards = [("Tickets", len(all_rows))] + [(s.capitalize(), counts[s]) for s in audit_log.STATUSES]
    for col, (label, value) in zip(st.columns(len(cards)), cards):
        col.metric(label, value)
    f1, f2 = st.columns([1, 2])
    status = f1.selectbox("Status", ["all", *audit_log.STATUSES], key="status_filter")
    search = f2.text_input("Search", key="audit_search")
    rows = audit_log.recent(status=None if status == "all" else status)
    if search:
        rows = [r for r in rows if search.lower() in " ".join(map(str, r.values())).lower()]

    def baseline_label(r):
        c = r.get("comparison")
        if not c:
            return ""
        if c.get("error"):
            return "failed"
        if c["action"] == r["action"] and (c["action"] != "answer" or c["result_hash"] == r["result_hash"]):
            return "same result"
        return f"different ({c['action']}, {c['row_count']} rows)" if c["action"] == "answer" else f"different ({c['action']})"

    if rows:
        df = pd.DataFrame([{
            "Time": r["ts"][5:16], "Requester": f"{r['requester']} · {r['role']}", "Question": r["question"],
            "Setup": f"{MODEL_ONLY.get(r['setup'], r['setup'])} ({r['setup']})", "Action": r["action"], "Status": r["status"],
            "Reviewed by": (r["approved_by"] or "").split("@")[0], "Baseline (S1)": baseline_label(r),
        } for r in rows])
        cfg = st.column_config
        # Widths sum to ~990 px so every column fits the content area at 1440 px with the sidebar open.
        st.dataframe(df, width="stretch", hide_index=True, column_config={
            "Time": cfg.TextColumn(width=85), "Requester": cfg.TextColumn("Requester · role", width=185),
            "Question": cfg.TextColumn(width=190), "Setup": cfg.TextColumn(width=170), "Action": cfg.TextColumn(width=60),
            "Status": cfg.TextColumn(width=115), "Reviewed by": cfg.TextColumn(width=85),
            "Baseline (S1)": cfg.TextColumn(width=100, help="Baseline result on the same ticket (compare mode)"),
        })
        st.caption("In compare mode the row is the QueryForge answer (GLM 5.3 Flash + harness) and the baseline "
                   "(GLM 5.3 Flash, S1) result is stored on the same row.")
    else:
        st.write("No tickets match.")
