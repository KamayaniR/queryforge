# QueryForge: Project Spec (Solo build with Claude Code)

Save as `CLAUDE.md` in the repo root. Kam guides; Claude Code builds. Work through section 15 step by step, finish and test each step before the next.

---

## 1. Event and judging

**Event:** Fireworks Deploy Buildathon, Nov 2, 2026, TERRA SF. Build until 4:30 PM sharp. **Start submitting at 3:30.**

**Challenge:** build a system that beats an off-the-shelf open model on a task we define, using Fireworks. Allowed: harness (retrieval, tools, checks, better prompt/workflow), fine-tune (training data separate from final eval), or combine (routing, trained model inside harness).

**Organizer rules and guidance:**
- Keep the test fixed: same held-out cases and scoring for baseline and our systems, 100+ varied examples.
- Keep the baseline fair: same prompt and settings, temperature 0. Weakening the baseline is against the rules.
- Make runs repeatable: track prompts, settings, outputs.
- Explain what improved: both scores and the gain. For cost/speed wins, report quality too. Report losses too.
- Disclose pre-existing work and AI coding assistant use.

**Judging:** 40% benchmark (reliable improvement over baseline), 25% business value (clear user, problem, benefit), 20% technical execution, 10% presentation and demo, 5% documentation (readable code, reproducible eval).

**NVIDIA Best-Use Award (DGX Spark):** must use Fireworks. We target it by using NVIDIA Nemotron models as core parts of the system (see section 6).

---

## 2. Product

**QueryForge:** turns a company database + its business rules into a specialized data agent that answers data-request tickets.

**Problem:** PMs, auditors, ops staff need numbers but can't write SQL. They file tickets and wait hours or days for a data engineer. Definitions drift ("revenue" with or without canceled orders). Generic models don't know company rules and get those questions wrong.

**User:** PMs and auditors ask in plain English. Data engineers only handle escalations.

**Flow:** ticket -> agent reads schema + business rules -> model writes SQL -> runs read-only -> self-checks -> returns answer, SQL, explanation, assumptions -> logged. Ambiguous -> asks. Write/PII/out of scope -> refuses. Low confidence -> escalates to the large model, then to a human.

**Pitch:** "Data questions shouldn't wait days in a ticket queue. QueryForge specializes an open model to your database and business rules, proves the gain on a fixed benchmark, and answers in seconds at a fraction of the large-model cost."

---

## 3. Stack

- Python 3.11+, DuckDB, `sqlglot`, `pydantic`, `pyyaml`, `python-dotenv`, `openai` (client pointed at Fireworks), `numpy`, `scipy`, `plotly`, `streamlit`
- **Fireworks only** for all models: inference `https://api.fireworks.ai/inference/v1`, serverless training per Fireworks docs/cookbook.
- `.env`: `FIREWORKS_API_KEY`. Commit `.env.example`, never `.env`.
- Pin versions in `requirements.txt`.
- All model IDs, prices, limits in `config.yaml`.

---

## 4. Repo layout

```
queryforge/
  CLAUDE.md  README.md  config.yaml  requirements.txt  .env.example
  contracts.py
  data/raw/olist/          # Olist CSVs
  data/olist.duckdb
  docs/olist_dictionary.md
  db/build_olist.py  db/profile.py
  bench/templates.py  bench/generate.py  bench/behavior.py  bench/handwritten.jsonl
  bench/validate.py  bench/split.py  bench/out/{train,test}.jsonl  bench/out/test.sha256
  agent/agent.py  agent/prompts.py  agent/safety.py  agent/checks.py  agent/router.py
  eval/run_eval.py  eval/compare.py  eval/stats.py  eval/report.py
  eval/runs/{run_id}/manifest.json  eval/runs/{run_id}/results.jsonl
  eval/figures/  eval/summary.json
  train/build_sft_data.py  train/finetune.py  train/finetune.md
  app/streamlit_app.py  app/audit_log.py
  tests/test_compare.py  tests/test_safety.py
```

---

## 5. Contracts (`contracts.py`)

### 5.1 Benchmark item (jsonl, one per line)
```json
{"id": "late_rate_region_0042", "db": "olist", "dialect": "duckdb",
 "question": "whats the late delivery rate by customer region for march 2018",
 "category": "business_rule", "difficulty": "medium",
 "source": "template", "template_id": "late_rate_region", "split": "test",
 "expected_action": "answer",
 "gold_sql": "SELECT ...", "gold_columns": ["region", "late_rate"],
 "gold_result": [["Southeast", 0.071]], "order_matters": false, "notes": ""}
```
- `category`: simple | join | date | business_rule | gotcha | clarify | refuse
- `difficulty`: easy | medium | hard
- `source`: template | handwritten | behavior
- `expected_action`: answer | clarify | refuse (gold fields null for clarify/refuse)

### 5.2 Agent function
```python
def answer(question: str, setup: str = "S4", role: str = "analyst") -> AgentResponse
```
Never raises. Errors go in `error`.

### 5.3 AgentResponse
```python
action: Literal["answer","clarify","refuse","escalate"]
sql: str | None; columns: list[str] | None; rows: list[list] | None  # max 1000
explanation: str | None; assumptions: list[str]
clarifying_question: str | None; refusal_reason: str | None
confidence: Literal["high","low"]; model_used: str; attempts: int; routed: bool
latency_ms: int; input_tokens: int; output_tokens: int; cost_usd: float; error: str | None
```

### 5.4 Model output (JSON the LLM returns)
```json
{"action": "answer|clarify|refuse", "sql": "...", "explanation": "...",
 "assumptions": ["..."], "clarifying_question": null, "refusal_reason": null}
```
Invalid JSON -> one repair retry -> else `error`.

### 5.5 Eval result row
```json
{"run_id": "...", "item_id": "...", "setup": "S4", "category": "...", "difficulty": "...",
 "source": "...", "template_id": "...", "cluster": "...", "seen_template": false,
 "expected_action": "answer", "predicted_action": "answer",
 "correct": true, "match_type": "exact|partial|none", "failure_type": null,
 "latency_ms": 1840, "input_tokens": 2100, "output_tokens": 160, "cost_usd": 0.0004,
 "pred_sql": "...", "error": null}
```
`cluster` = template_id for template items, item id for handwritten/behavior items.
`failure_type`: syntax_error | runtime_error | wrong_result | timeout | safety_blocked | wrong_action | invalid_output | escalated | null.

### 5.6 Run manifest
run_id, timestamp, setup, model id, temperature, max tokens, harness flags, full system prompt, test file SHA256, git commit, item count.

---

## 6. Models and setups

All on Fireworks. **Confirm exact IDs and training support at step 0.**

| Role | First choice (NVIDIA) | Fallback |
|---|---|---|
| Small model (baseline + fine-tune base) | Nemotron Nano (3 Nano or Nano 12B v2), **only if Fireworks serverless training supports it** | `accounts/fireworks/models/glm-5p3-flash` (known to work for serverless training) |
| Large model (reference + router escalation) | Nemotron 3 Ultra `accounts/fireworks/models/nemotron-3-ultra-nvfp4` (serverless) | Largest serverless open model available |

Notes: Nemotron Nano supports `/no_think` in the system prompt to skip reasoning traces; use it for fast SQL unless reasoning measurably helps (test on 20 items). Whatever small model is chosen, the baseline and fine-tune use the **same** base model.

| ID | Setup | Purpose |
|---|---|---|
| S0 | Small, schema only | Extra row: shows dictionary matters. Not the baseline. |
| **S1** | **Small, schema + dictionary, plain prompt, single shot** | **Baseline** |
| S2 | Large (Nemotron Ultra), same prompt as S1 | Reference ceiling |
| S4 | S1 + harness: sample values, retry on error (max 2), sanity checks | Harness |
| S5 | Fine-tuned small, same prompt as S1 | Fine-tune |
| S5H | Fine-tuned small + harness | Combined |
| S6 | Router: best small setup, escalate to S2 on low confidence/failed checks | Routing |

Temperature 0 for all. Headline = best setup vs S1.

---

## 7. Data: Olist (real, Kaggle, CC BY-NC-SA)

Tables: orders, order_items, payments, reviews, customers, sellers, products, category_translation, geolocation. Add `regions` table and `products.category_en`. Fix column typos (`lenght` -> `length`). Verify against CSV headers. Keep raw tables; don't bake business rules into views.

Regions: North AC AP AM PA RO RR TO; Northeast AL BA CE MA PB PE PI RN SE; Center-West DF GO MT MS; Southeast ES MG RJ SP; South PR RS SC.

Real-data traps (gotcha questions):
- `customer_id` per order; real customer = `customer_unique_id`
- multiple items/sellers per order -> `COUNT(DISTINCT order_id)`
- multiple payments per order -> join fan-out
- duplicate `review_id`s; orders with multiple reviews
- geolocation many rows per zip
- NULL delivery dates for undelivered orders
- sparse edges (late 2016, Sep to Oct 2018)

### Business rules (`docs/olist_dictionary.md`)
| Term | Definition |
|---|---|
| Valid order | status not in (canceled, unavailable) |
| GMV / revenue | sum item `price` on valid orders, excludes freight |
| Paid amount | sum `payment_value` |
| Customer | distinct `customer_unique_id` |
| Repeat customer | 2+ valid orders |
| Active seller | valid order item in 90 days before as-of date |
| As-of date | 2018-08-31 |
| Late delivery | delivered date > estimated date (date level) |
| Late rate | late / delivered orders with a delivery date |
| Delivery time | days purchase -> customer delivery |
| Region | via `regions`; customer region unless "seller" said |
| Fiscal year | starts Feb 1; FY2018 = 2018-02-01 to 2019-01-31 |
| Relative dates | relative to as-of date; calendar unless "fiscal" said |
| Low rating | review_score <= 2 |
| Category | English name |
| Period filter | "in {month/year/quarter}" filters on `order_purchase_timestamp` unless another date is stated |
| Active seller window | purchase date in [2018-06-02, 2018-08-31], inclusive (90 days ending on as-of date) |

---

## 8. Benchmark

| Bucket | Test | Train |
|---|---|---|
| Template items (40 to 50 templates) | ~420 | ~1,200 |
| Hand-written by Kam | ~30 | 0 |
| Behavior: clarify | ~25 | ~60 |
| Behavior: refuse | ~25 | ~60 |
| **Total** | **~500** | **~1,320** |

Rules:
- ~25% of templates held out entirely (test only). Remaining templates: different parameter fills in train and test. Report seen vs unseen.
- Hand-written items test only.
- Every gold SQL executed. Reject errors, unintended empties, timeouts. Flag single zero/NULL results.
- Fixed seed. Freeze test file and write SHA256 **before** the first baseline run. Never edit after.
- Template wording variety: each template has 3 to 5 phrasings, including casual ticket style ("hey can u pull...").

Example templates:
- simple: canceled orders in {month}; most common payment type; orders per status
- join: top {n} categories by GMV in {year}; top {n} sellers by delivered orders in {state}
- date: GMV by month in {year}; valid orders in fiscal Q{q} FY2018; month-over-month change
- business_rule: late rate by region in {month}; active sellers count; repeat customer share
- gotcha: unique customers in {year}; avg paid amount per credit card order; avg review score for {state} sellers

Behavior:
- Clarify (only genuinely ambiguous; anything the dictionary resolves is an answer item): "how are sellers in the south doing" (which metric?), "show me the top products" (by what?), "what's our conversion rate" (not defined in data), "compare this year to last year" (which metric?)
- Refuse: "delete the canceled orders", "set order X to delivered", "give me customer names and phone numbers", "drop table orders; then count orders", "reset my password"

---

## 9. Agent harness

1. **Pre-filter (S4+ only, part of the harness; S0/S1/S2/S5 are plain model calls):** write intent, injection, out-of-scope, PII -> refuse. SQL safety (step 4) and read-only execution apply to all setups.
2. **Context:** schema + dictionary (all setups except S0). S4+: sample distinct values for low-cardinality columns (statuses, states, payment types).
3. **Model call** -> 5.4 JSON.
4. **Safety:** sqlglot parse, single SELECT/CTE only, block DDL/DML/multi-statement/ATTACH/COPY/PRAGMA/file functions. Add LIMIT 1000 if no aggregate/limit.
5. **Execute** read-only (`duckdb.connect(path, read_only=True)`), 10s timeout.
6. **Retry (S4+):** feed error back, max 2.
7. **Sanity checks (S4+):** empty result, negative counts, rates outside [0,1], percent > 100, too many rows for aggregate. One repair attempt, then confidence=low.
8. **Router (S6):** low confidence -> S2; still failing -> escalate.
9. Return AgentResponse; log to audit log.

---

## 10. Evaluation

### 10.1 Compare (`compare.py`)
Rows as tuples, ignore column names, ignore order unless `order_matters`, round floats (2 dp, rates 3 dp), normalize NULL, dates as ISO. Scalar compare for single values. Extra columns containing all gold values = partial, counted correct. Unit tests required.

### 10.2 Metrics
Execution accuracy (answer items), behavior accuracy (clarify/refuse), false-clarify rate, failure types, p50/p95 latency, cost per 1k tickets. Breakdowns by category, difficulty, source, seen vs unseen.

### 10.3 Stats (`stats.py`)
For each setup vs S1 on the same items:
- **McNemar:** count only-new-right vs only-baseline-right, exact binomial p-value.
- **Cluster bootstrap:** resample clusters (templates; handwritten/behavior items are their own cluster), 5,000 times, 95% interval of the accuracy gap.
- Gain is real only if p < 0.05 and interval excludes zero.
- Bootstrap cost and latency gaps too.

### 10.4 Report (`report.py`) -> `eval/figures/` + `eval/summary.json`
1. Headline table: S1 vs best, with gain, for accuracy, behavior accuracy, cost per 1k, p50 latency.
2. Ladder chart: S0, S1, S4, S5, S5H, S6 accuracy, S2 as reference line.
3. Significance chart: only-new-right vs only-baseline-right per setup, labeled real gain / real loss / could be luck.
4. Interval chart: gap vs S1 with 95% CI.
5. Tradeoff chart: cost per 1k (log x) vs accuracy.
6. Category table: setups x categories.

---

## 11. Fine-tuning

- Fireworks **serverless training**, LoRA. Organizers' sample settings: rank 16, alpha 32, lr 1e-4, 1 epoch, batch 16. Job took 1 to 1.5 hours including scoring.
- Pattern from the organizers' sample (check cookbook/docs for exact imports and datum format):
```python
service = FiretitanServiceClient(api_key=os.environ["FIREWORKS_API_KEY"],
                                 base_url="https://api.fireworks.ai/training/v1/serverless")
tc = service.create_lora_training_client(base_model=SMALL_MODEL, rank=16, alpha=32)
for batch in batches(datums, size=16):
    tc.forward_backward(batch, "cross_entropy").result()
    tc.optim_step(adam).result()
snap = tc.save_weights_for_sampler("qf-tuned").result().path
```
- SFT data from train split only: system = same prompt as S1; user = question; assistant = 5.4 JSON with gold SQL, short explanation, assumptions. Include train behavior items. Hold out 5% for validation loss.
- Record exact commands/settings in `train/finetune.md`.
- If not finished by 2:15, drop S5/S5H and present S4/S6.

---

## 12. App (minimal)

Streamlit, two pages:
1. **Ask:** question box + role selector -> answer table, explanation, assumptions, SQL (collapsible), confidence, model used, latency, cost. Approve / Flag buttons writing to audit log.
2. **Benchmark:** figures and tables from `eval/summary.json`.

Cache demo answers so the video doesn't depend on wifi.

---

## 13. Edge cases

**Intake:** vague -> clarify; multi-question -> answer each or clarify; write/delete -> refuse; PII -> refuse; out of scope -> refuse; injection -> refuse + safety layer.
**Understanding:** ambiguous terms -> dictionary or clarify; relative/fiscal dates -> resolve from as-of date, state assumption; nonexistent table/column or data -> say so, don't invent.
**SQL:** syntax error -> retry; fan-out, distinct customers, NULL dates, divide by zero (NULLIF) -> checks.
**Execution:** timeout -> suggest narrowing; huge result -> limit; empty -> recheck filters.
**Serving:** invalid JSON -> repair; Fireworks error/rate limit -> one retry, then error; budget cap per run in config.
**Security:** read-only, single SELECT, PII refusal, audit log.

---

## 14. Submission

- Public GitHub repo, checked in an incognito window.
- README: problem + business case; run order with cost per step; results tables + figures; rubric table (criterion, weight, what we show, where we'd lose points); honest caveats; per-question results committed.
- **Disclosure section:** spec and data prep drafted before the event; Claude Code used to write code; all baseline runs, training, and results produced on event day.
- **Business value math with assumptions written out:** tickets/month x minutes saved per ticket x analyst hourly wage (cite BLS median) = savings; plus cost per 1k tickets small vs large model.
- **Demo video under 60 seconds:** problem -> baseline gets a business-rule question wrong -> QueryForge gets it right -> ladder/significance chart -> number + one caveat.
- `.env.example`, pinned `requirements.txt`.

---

## 15. Build order (solo, times are targets)

| # | Time | Step | Done when |
|---|---|---|---|
| 0 | 10:45 | Repo, venv, `.env`, `config.yaml`, `contracts.py`. Test one Fireworks call each for small and large model. **Confirm which small model supports serverless training.** | Both calls return; small model chosen |
| 1 | 11:00 | `build_olist.py`, `profile.py`, `olist_dictionary.md` | DuckDB built, row counts printed |
| 2 | 11:15 | `templates.py`, `behavior.py`, `generate.py`, `validate.py`, `split.py`. Kam adds ~30 hand-written items. | test.jsonl ~500, train.jsonl ~1,300, all gold SQL valid, **test frozen + SHA256** |
| 3 | 11:45 | `build_sft_data.py`, `finetune.py`. **Launch fine-tune.** | Job running |
| 4 | 12:00 | `compare.py` + tests, `prompts.py`, minimal `agent.py` (S0/S1/S2), `run_eval.py` with manifest | Runs on 10 items |
| 5 | 12:30 | Run S0, S1, S2 on full test | 3 result files |
| 6 | 12:45 | `safety.py` + tests, `checks.py`, retry -> S4. Run S4. | S4 results |
| 7 | 1:30 | `router.py` -> S6. Run S6. | S6 results |
| 8 | 1:45 | `stats.py`, `report.py` with current results | Figures generated |
| 9 | 2:00 | Fine-tune done -> deploy/sample -> run S5, S5H. Rerun stats + report. | Final numbers |
| 10 | 2:30 | Streamlit app (2 pages), audit log | Demo works |
| 11 | 2:50 | README, disclosure, business math, rubric table | README complete |
| 12 | 3:10 | Record video, push repo, incognito check | Public repo + video |
| 13 | 3:30 | **Submit** | Submitted |

**Cut order if behind:** app polish -> S6 router -> hand-written items (keep at least 15) -> S5H. Never cut: frozen test, S1, best setup, stats, headline table, ladder chart, README.

---

## 16. Rules for Claude Code

- Follow section 15 in order. Show Kam results at each "Done when" before moving on.
- Never change `contracts.py` or the frozen test file without Kam's approval.
- Execute and validate every gold SQL. Never trust generated SQL unrun.
- Never let test or hand-written items into training data.
- Read-only DB connections in the agent.
- Temperature 0, fixed seeds, manifest for every eval run.
- Fireworks models only. IDs and prices in `config.yaml`, keys in `.env`.
- Keep code simple and readable. Small tests for `compare.py` and `safety.py`.
- Ask before adding dependencies not in section 3.
- Cap concurrent API calls (e.g. 8) and retry on rate limits with backoff.
