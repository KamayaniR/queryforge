"""The QueryForge agent harness (CLAUDE.md section 9).

One code path for every setup; config.yaml `setups` toggles the model, the
dictionary, the harness (pre-filter, sample values, retry, sanity checks) and
the router. `answer()` never raises: errors go in AgentResponse.error as
"<failure_type>: <message>".
"""
import json
import os
import re
import sys
import threading
import time
from pathlib import Path

import duckdb
import yaml
from dotenv import load_dotenv
from openai import OpenAI

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from agent import checks, prompts, safety  # noqa: E402
from contracts import AgentResponse, ModelOutput  # noqa: E402

load_dotenv(ROOT / ".env")
CFG = yaml.safe_load(open(ROOT / "config.yaml"))
DB_PATH = str(ROOT / CFG["paths"]["olist_db"])
LIM = CFG["limits"]
GEN = CFG["generation"]

_client = OpenAI(api_key=os.environ.get("FIREWORKS_API_KEY"), base_url=CFG["fireworks"]["inference_base_url"],
                 max_retries=3, timeout=GEN["request_timeout_s"])
_local = threading.local()


def _con():
    """Per-thread read-only DuckDB connection with external file access disabled."""
    if not hasattr(_local, "con"):
        _local.con = duckdb.connect(DB_PATH, read_only=True, config={"enable_external_access": False})
    return _local.con


_TABLES = {r[0] for r in duckdb.connect(DB_PATH, read_only=True).execute(
    "SELECT table_name FROM information_schema.tables").fetchall()}


def _sample_values() -> str:
    con = duckdb.connect(DB_PATH, read_only=True)
    cols = [("orders", "order_status"), ("payments", "payment_type"), ("customers", "customer_state"),
            ("sellers", "seller_state"), ("regions", "region"), ("products", "category_en"),
            ("reviews", "review_score")]
    lines = []
    for t, c in cols:
        vals = [str(r[0]) for r in con.execute(f"SELECT DISTINCT {c} FROM {t} WHERE {c} IS NOT NULL ORDER BY 1").fetchall()]
        lines.append(f"- {t}.{c}: {', '.join(vals)}")
    return "\n".join(lines)


SAMPLE_VALUES = _sample_values()


class _Timeout(Exception):
    pass


def execute(sql: str):
    con = _con()
    timer = threading.Timer(LIM["sql_timeout_s"], con.interrupt)
    timer.start()
    try:
        cur = con.execute(sql)
        cols = [d[0] for d in cur.description]
        rows = [list(r) for r in cur.fetchmany(LIM["row_limit"])]
        return cols, rows
    except duckdb.InterruptException as e:
        raise _Timeout(f"query exceeded {LIM['sql_timeout_s']}s") from e
    finally:
        timer.cancel()


def _jsonable(rows):
    return json.loads(json.dumps(rows, default=str))


def parse_output(text: str) -> ModelOutput:
    t = (text or "").strip()
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t)
    start, end = t.find("{"), t.rfind("}")
    if start < 0 or end < 0:
        raise ValueError("no JSON object in model output")
    return ModelOutput(**json.loads(t[start:end + 1]))


class _Call:
    """Tracks tokens, cost and attempts across the model calls of one ticket."""

    def __init__(self, model_key: str):
        m = CFG["models"][model_key]
        self.model_id, self.extra = m["id"], m.get("extra_body") or {}
        self.p_in, self.p_out = m["price_in"] or 0, m["price_out"] or 0
        self.in_tok = self.out_tok = self.attempts = 0

    @property
    def cost(self):
        return (self.in_tok * self.p_in + self.out_tok * self.p_out) / 1e6

    def __call__(self, messages) -> str:
        self.attempts += 1
        r = _client.chat.completions.create(model=self.model_id, messages=messages, temperature=GEN["temperature"],
                                            max_tokens=GEN["max_tokens"], extra_body=self.extra or None)
        self.in_tok += r.usage.prompt_tokens
        self.out_tok += r.usage.completion_tokens
        return r.choices[0].message.content or ""


def _classify(e: Exception) -> str:
    if isinstance(e, safety.UnsafeSQL):
        return "safety_blocked"
    if isinstance(e, (SyntaxError, duckdb.ParserException)):
        return "syntax_error"
    if isinstance(e, _Timeout):
        return "timeout"
    return "runtime_error"


def _run_single(question: str, setup: str) -> AgentResponse:
    s = CFG["setups"][setup]
    harness = s["harness"]
    t0 = time.time()
    call = _Call(s["model"])
    resp = AgentResponse(action="answer", model_used=call.model_id)

    def finish(**kw):
        for k, v in kw.items():
            setattr(resp, k, v)
        resp.attempts, resp.input_tokens, resp.output_tokens = call.attempts, call.in_tok, call.out_tok
        resp.cost_usd, resp.latency_ms = call.cost, int((time.time() - t0) * 1000)
        return resp

    if harness:
        reason = safety.prefilter(question)
        if reason:
            return finish(action="refuse", refusal_reason=reason)

    system = prompts.system_prompt(dictionary=s["dictionary"], sample_values=SAMPLE_VALUES if harness else None)
    messages = [{"role": "system", "content": system}, {"role": "user", "content": question}]

    def ask():
        """One model call plus one JSON repair retry (contracts 5.4)."""
        text = call(messages)
        try:
            out = parse_output(text)
        except Exception as e:  # noqa: BLE001
            messages.extend([{"role": "assistant", "content": text},
                             {"role": "user", "content": f"Your reply was not valid JSON ({e}). Reply with only the JSON object."}])
            text = call(messages)
            out = parse_output(text)
        messages.append({"role": "assistant", "content": text})
        return out

    try:
        out = ask()
    except Exception as e:  # noqa: BLE001
        return finish(error=f"invalid_output: {e}")

    sql_retries = LIM["max_sql_retries"] if harness else 0
    repaired = False
    while True:
        resp.explanation, resp.assumptions = out.explanation, out.assumptions
        if out.action != "answer":
            return finish(action=out.action, sql=out.sql, clarifying_question=out.clarifying_question,
                          refusal_reason=out.refusal_reason, error=None)
        resp.sql = out.sql
        try:
            safe_sql = safety.check_sql(out.sql or "", _TABLES, row_limit=LIM["row_limit"])
            cols, rows = execute(safe_sql)
        except Exception as e:  # noqa: BLE001
            kind = _classify(e)
            if sql_retries > 0 and kind != "safety_blocked":
                sql_retries -= 1
                messages.append({"role": "user", "content": f"The query failed with: {e}\nFix it and reply with the JSON object."})
                try:
                    out = ask()
                    continue
                except Exception as e2:  # noqa: BLE001
                    return finish(error=f"invalid_output: {e2}", confidence="low")
            return finish(error=f"{kind}: {str(e)[:300]}", confidence="low")

        rows = _jsonable(rows)
        if harness:
            warnings = checks.sanity(question, cols, rows)
            if warnings and not repaired:
                repaired = True
                messages.append({"role": "user", "content": "Sanity check warnings on the result:\n- " + "\n- ".join(warnings)
                                 + f"\nFirst rows: {rows[:5]}\nIf the query is wrong, fix it. If it is right, return the same JSON."})
                try:
                    out = ask()
                    continue
                except Exception:  # noqa: BLE001
                    return finish(columns=cols, rows=rows, confidence="low", error=None)
            if warnings:
                return finish(columns=cols, rows=rows, confidence="low", error=None)
        return finish(columns=cols, rows=rows, confidence="high", error=None)


def answer(question: str, setup: str = "S4", role: str = "analyst") -> AgentResponse:
    """Answer one ticket. Never raises."""
    try:
        s = CFG["setups"][setup]
        if not s.get("router"):
            return _run_single(question, setup)
        base = _run_single(question, s["base"])
        if base.confidence == "high" and not base.error:
            return base
        big = _run_single(question, s["escalate_to"])
        big.routed = True
        big.attempts += base.attempts
        big.input_tokens += base.input_tokens
        big.output_tokens += base.output_tokens
        big.cost_usd += base.cost_usd
        big.latency_ms += base.latency_ms
        if big.error:
            big.action, big.confidence = "escalate", "low"
            big.error = f"escalated: {big.error}"
        return big
    except Exception as e:  # noqa: BLE001
        return AgentResponse(action="answer", error=f"runtime_error: {type(e).__name__}: {e}", confidence="low")


if __name__ == "__main__":
    q = sys.argv[1] if len(sys.argv) > 1 else "What was GMV in March 2018?"
    setup = sys.argv[2] if len(sys.argv) > 2 else "S1"
    print(answer(q, setup).model_dump_json(indent=1))
