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
ALL_SETUP_NAMES = {"S0": "Schema only (S0)", "S5": "Fine-tuned (S5)", **SETUP_NAMES}
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
               ("Cost", f"${resp.cost_usd:.5f}"), ("Action", resp.action)]
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
    st.markdown("**Try an example ticket**")

    def use_example(question):
        st.session_state["ticket"] = question
        st.session_state["auto_submit"] = True

    for col, (label, question) in zip(st.columns(len(EXAMPLES)), EXAMPLES):
        col.button(label, key=f"ex_{label}", on_click=use_example, args=(question,), width="stretch", help=question)

    st.session_state.setdefault("ticket", "whats the late delivery rate by customer region for last month")
    q = st.text_area("Ticket", height=90, key="ticket")
    t1, t2 = st.columns(2)
    compare_mode = t1.toggle("Compare Baseline (S1) vs QueryForge (S4)", value=True, key="compare")
    use_cache = t2.toggle("Use cached demo answers", value=True)
    example_click = st.session_state.pop("auto_submit", False)
    if (st.button("Submit ticket", type="primary") or example_click) and q.strip():
        setups = ["S1", "S4"] if compare_mode else [setup]
        results = []
        with st.spinner("Writing and running SQL..."):
            for s in setups:
                resp = cached_or_live(q, s, use_cache or example_click)
                results.append((s, audit_log.log_ticket(resp, q, s, requester, role), resp))
        st.session_state["results"] = results
        st.session_state["asked"] = q

    def approve_flag(tid, key):
        a, b = st.columns(2)
        if a.button("Approve", key=f"approve_{key}"):
            audit_log.set_status(tid, "approved", requester)
            st.success("Approved and logged.")
        if b.button("Flag for data engineer", key=f"flag_{key}"):
            audit_log.set_status(tid, "flagged", requester)
            st.warning("Flagged for review.")

    results = st.session_state.get("results", [])
    if len(results) > 1:
        for col, (s, tid, resp) in zip(st.columns(len(results), gap="large"), results):
            with col:
                st.subheader(SETUP_NAMES[s])
                render_answer(resp, tid, compact=True, question=st.session_state.get("asked", ""))
                approve_flag(tid, tid)
    elif results:
        s, tid, resp = results[0]
        st.subheader(SETUP_NAMES[s])
        render_answer(resp, tid, question=st.session_state.get("asked", ""))
        approve_flag(tid, tid)

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

        c[0].metric("Accuracy: Baseline → QueryForge", f"{100 * s4['base_acc']:.1f}% → {100 * s4['new_acc']:.1f}%",
                    f"{gap_pts(s4):+.1f} pts · p = {s4['p_value']:.4f}")
        c[1].metric("QueryForge vs Nemotron Ultra", f"{gap_pts(s4_s2):+.1f} pts",
                    f"{100 * s4_s2['base_acc']:.1f}% → {100 * s4_s2['new_acc']:.1f}% · p < 0.001"
                    if s4_s2["p_value"] < 0.001 else f"p = {s4_s2['p_value']:.3f}")
        c[2].metric("Cost per 1k tickets (QueryForge)", f"${cost['S4']:.2f}",
                    f"S1 ${cost['S1']:.2f} · S2 ${cost['S2']:.2f}", delta_color="off")
        c[3].metric("Est. monthly savings", f"~${round(savings, -1):,.0f}",
                    f"{tickets} tickets × {int(resolved * 100)}% × {minutes_saved} min × ${wage}/h", delta_color="off")
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
        st.caption("Paired against the S1 baseline on the same 30 questions. n = 30 is small: treat these as directional.")
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
    st.caption("Every submitted ticket is logged. Approve / Flag on the Ask page update the status here.")
    all_rows = audit_log.recent()
    counts = {s: sum(r["status"] == s for r in all_rows) for s in audit_log.STATUSES}
    c = st.columns(4)
    c[0].metric("Tickets", len(all_rows))
    for col, s in zip(c[1:], audit_log.STATUSES):
        col.metric(s.capitalize(), counts[s])
    f1, f2 = st.columns([1, 2])
    status = f1.selectbox("Status", ["all", *audit_log.STATUSES], key="status_filter")
    search = f2.text_input("Search", key="audit_search")
    rows = audit_log.recent(status=None if status == "all" else status)
    if search:
        rows = [r for r in rows if search.lower() in " ".join(map(str, r.values())).lower()]
    if rows:
        df = pd.DataFrame(rows)[["ts", "requester", "role", "question", "setup", "action", "status", "approved_by"]]
        df["setup"] = df["setup"].map(lambda s: ALL_SETUP_NAMES.get(s, s))
        df["approved_by"] = df["approved_by"].fillna("")
        df = df.rename(columns={"ts": "Timestamp", "requester": "Requester", "role": "Role", "question": "Question",
                                "setup": "Setup", "action": "Action", "status": "Status", "approved_by": "Reviewed by"})
        st.dataframe(df, width="stretch", hide_index=True)
    else:
        st.write("No tickets match.")
