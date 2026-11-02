# QueryForge

**Turns a company database plus its business rules into a data agent that answers data-request tickets in seconds, and proves the gain on a fixed benchmark.**

Built for the Fireworks Deploy Buildathon (Nov 2, 2026). Every model runs on Fireworks: GLM 5.3 Flash as the small model, NVIDIA Nemotron 3 Ultra as the large reference and escalation tier, and a LoRA fine-tune trained with Fireworks serverless training.

---

## The problem

PMs, auditors and ops staff need numbers, but they can't write SQL. They file a ticket and wait hours or days for a data engineer. Definitions drift too: is "revenue" with or without canceled orders? Who counts as a "customer"? Generic models don't know a company's rules, so they get exactly those questions wrong.

**User:** a PM or auditor asks in plain English. **Benefit:** an answer in about 3 seconds, with the SQL, an explanation and the assumptions it made. Every answer is logged. Data engineers only see tickets the agent escalates or a person flags.

```
ticket ─► pre-filter ─► model writes SQL ─► safety check ─► read-only DuckDB ─► sanity checks ─► answer + SQL + assumptions ─► audit log
            │ (write/PII/injection → refuse)       │ (error → retry ×2)        │ (warning → 1 repair, else low confidence)
            └── ambiguous → asks a clarifying question            low confidence → router escalates to Nemotron Ultra → then a human
```

## Results

<!-- RESULTS:START -->
*(filled from `eval/results.md` by the final report run)*
<!-- RESULTS:END -->

![Accuracy ladder](eval/figures/ladder.png)
![Significance vs baseline](eval/figures/significance.png)
![Gap vs baseline with 95% CI](eval/figures/intervals.png)
![Quality vs cost](eval/figures/tradeoff.png)
![Seen vs held-out templates vs hand-written](eval/figures/seen_unseen.png)

Per-question results for every run are committed under `eval/runs/{setup}_{test|hw}/results.jsonl`, each next to a `manifest.json` that records the full system prompt, model, settings, test-file SHA256 and git commit.

## What we found

<!-- FINDINGS:START -->
*(filled after the final runs)*
<!-- FINDINGS:END -->

## Business value

Assumptions, all stated:
- **Volume:** 200 data tickets a month for a mid-size team.
- **Time without QueryForge:** a data engineer spends about 30 minutes per ticket (understand it, write and check the SQL, reply), and the requester waits 1 to 3 days in the queue.
- **Time with QueryForge:** the requester reviews the answer, SQL and assumptions in about 5 minutes. Low-confidence answers and flagged tickets still go to an engineer (about 5–10% of tickets at S4's accuracy).
- **Wage:** US median pay for data scientists, **$54.13 per hour** ([BLS Occupational Outlook Handbook, 2024](https://www.bls.gov/ooh/math/data-scientists.htm)).

| | Per ticket | Per month (200 tickets) |
|---|---|---|
| Engineer time saved (30 → 5 min, ~90% of tickets) | ~$20 | **~$4,000** (about 75 engineer-hours) |
| Model cost, QueryForge S4 (GLM 5.3 Flash + harness) | $0.0005 | $0.10 |
| Model cost, Nemotron 3 Ultra alone (S2) | $0.0026 | $0.52 |
| Turnaround | days → ~3 s | |

At this volume the model bill is negligible. The value is engineer time and turnaround. QueryForge also beats the large model on accuracy (S4 vs S2) at about a fifth of the model cost and less than half the latency.

## The benchmark

**Data:** [Olist Brazilian e-commerce](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce): 99k real orders across 9 tables (CC BY-NC-SA). It's loaded into DuckDB with column typos fixed, a `regions` table and an English `category_en` column. Business rules are deliberately **not** baked into views. `db/profile.py` confirms the real-data traps:

| Trap | Evidence in the data |
|---|---|
| `customer_id` is per order | 99,441 customer_ids, but only 96,096 real customers (`customer_unique_id`) |
| Multi-item / multi-seller orders | 9,803 orders with more than 1 item, 1,278 with more than 1 seller |
| Multiple payments per order | 2,961 orders |
| Duplicate reviews | 789 duplicate `review_id`s, 547 orders with more than 1 review |
| Geolocation fan-out | 52.6 rows per zip prefix |

**Business rules** ([docs/olist_dictionary.md](docs/olist_dictionary.md), given to every setup except S0): valid order, GMV, paid amount, customer, repeat customer, active seller (90 days before the as-of date 2018-08-31), late delivery, late rate, delivery time, region, fiscal year (starts Feb 1), relative dates, low rating, plus output conventions.

**Test sets.** Both are frozen with SHA256 before any setup ran on them, and never edited afterwards. `run_eval.py` refuses to run if a hash doesn't match.

| File | Items | What it is |
|---|---|---|
| `bench/out/test.jsonl` | 416 | See breakdown below |
| `bench/out/test_handwritten.jsonl` | 30 | Written by Kam in ticket style without looking at the templates. Gold SQL written to the dictionary, with interpretations in `notes` |

`test.jsonl` holds:
- **226 template items from 31 seen templates.** Train and test never share a value combination for the same template.
- **140 items from 10 held-out templates** (about 25%, stratified by category), which never appear in training.
- **25 clarify and 25 refuse items.** These are hand-written, and the train-only behavior set uses different questions.

**Training set:** 1,350 items (1,230 template items plus 120 behavior items), all from the train split.

**Validation** (`bench/validate.py`):
- Every gold SQL query is re-executed and must reproduce its stored answer.
- Empty or zero results are dropped.
- Top-N questions with ties at the cut-off are dropped.
- 0 shared value combinations, 0 shared question texts, 0 held-out templates in train, and 0 test-only items in train.

**Scoring** ([eval/compare.py](eval/compare.py), unit-tested):
- Compares the executed result set to the gold result: column names and row order are ignored (unless order matters), and numbers have a tolerance of 0.001 for rates and 0.01 otherwise.
- Extra predicted columns that contain the gold columns count as a *partial* match, which is correct.
- Behavior items score on whether the action (`clarify` or `refuse`) matches.

**Statistics** ([eval/stats.py](eval/stats.py)), paired against S1 on the same items:
- An exact McNemar test.
- A cluster bootstrap that resamples templates (each hand-written or behavior item is its own cluster), 5,000 resamples, giving a 95% interval for the accuracy gap.
- A gain is called *real* only if p < 0.05 **and** the interval excludes 0.

## Setups

All setups run at temperature 0, with a 4,096-token cap and the same instructions. S1 is the baseline; nothing in it is weakened.

| ID | Setup |
|---|---|
| S0 | GLM 5.3 Flash, schema only (no business rules). Shows that the dictionary matters. |
| **S1** | **GLM 5.3 Flash, schema + dictionary, single shot. Baseline.** |
| S2 | NVIDIA Nemotron 3 Ultra, same prompt as S1. Large-model reference. |
| S4 | S1 plus the harness: pre-filter (write/PII/injection/out-of-scope), distinct values for low-cardinality columns in the prompt, SQL retry on error (max 2), and result sanity checks with one repair attempt. |
| S5 | GLM 5.3 Flash + LoRA fine-tune, same prompt as S1. |
| S5H | S5 plus the harness. |
| S6 | Router: S4, escalating to S2 when confidence is low or the run fails. |

The SQL safety layer and read-only execution apply to **every** setup:
- Parsing with sqlglot, allowing exactly one SELECT or CTE.
- Blocking DDL/DML, ATTACH, COPY, PRAGMA and file functions.
- A table allow-list.
- A DuckDB connection with `read_only=True` and `enable_external_access=false`.
- A 10-second timeout.

## Fine-tuning

LoRA SFT on Fireworks serverless training: rank 16, alpha 32, learning rate 1e-4, batch 16, 1 epoch over 1,283 examples (2.1M tokens, about $19). Validation loss fell from 0.82 to 0.012 and kept decreasing. The tuned model is trained to answer **without a reasoning trace**, while the base model always reasons. Full record, commands and the serving path are in [train/finetune.md](train/finetune.md).

## Reproduce

```bash
python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env               # add FIREWORKS_API_KEY
# put the Olist CSVs in data/raw/olist/
python db/build_olist.py && python db/profile.py                     # ~5 s, free
python bench/generate.py && python bench/split.py && python bench/validate.py
python bench/handwritten.py                                         # rebuilds the hand-written file; its hash must still match
python train/build_sft_data.py && python train/finetune.py           # ~75 min, ~$19
python -m pytest tests/                                             # comparer + safety tests
for s in S0 S1 S2 S4 S6 S5 S5H; do
  python eval/run_eval.py --setup $s --run-id ${s}_test
  python eval/run_eval.py --setup $s --split test_handwritten --run-id ${s}_hw
done
python eval/report.py                                               # tables + figures
streamlit run app/streamlit_app.py                                  # demo app
```

Cost of the event-day runs, test set (416 items):

| S0 | S1 | S2 | S4 | S6 | S5 |
|---|---|---|---|---|---|
| $0.16 | $0.19 | $1.07 | $0.21 | $0.22 | ~$0.15 |

The hand-written runs cost about $0.02 each.

## Rubric

| Criterion (weight) | What we show | Where we could lose points |
|---|---|---|
| Benchmark (40%) | A frozen 416 + 30 item test set on real data, with held-out templates, hand-written questions and behavior items. A fair baseline, paired McNemar tests and cluster-bootstrap intervals. Per-question results committed. | The baseline is strong (91%), so the headroom is about 9 points. Template questions are cleaner than real tickets. There's a single run per setup (temperature 0 but not bit-deterministic: about 1 point of run-to-run noise, from S4 vs S6). |
| Business value (25%) | A clear user and problem, stated assumptions, BLS wage, cost per 1k tickets. | The time savings are assumptions, not measured in a deployment. |
| Technical execution (20%) | One harness for all setups, SQL safety plus read-only execution, retry and sanity checks, a router, serverless LoRA training, manifests. | The fine-tuned model is served through the training sampler, not a production endpoint, so its latency isn't comparable. |
| Presentation (10%) | Streamlit app (Ask, Benchmark, Audit log) and a video under 60 seconds. | |
| Documentation (5%) | This README, `train/finetune.md`, tests, a pinned `requirements.txt`. | |

## Caveats

<!-- CAVEATS:START -->
- **The benchmark questions come from templates written by the same person who wrote the dictionary.** Held-out templates and the 30 hand-written questions are the checks against this.
- **The pre-filter patterns and the refuse items were written by the same author.** On the benchmark the pre-filter makes 0 false refusals and catches 20 of the 25 test refusals before any model call. Real traffic will be messier.
- **S5/S5H latency** is measured through the serverless training sampler, including a ~4 minute cold start per process. It isn't comparable to the chat-endpoint latency of the other setups. Tuned-model cost uses the base model's serverless token prices.
- **Single run per setup.** S4 and S6 share the same first stage, and their gap (about 1 point) is a rough estimate of run-to-run noise.
<!-- CAVEATS:END -->

## Disclosure

- **Before the event:** the project spec and the plan for data preparation.
- **Built with an AI assistant:** Claude Code (Anthropic) wrote the code, guided by Kam.
- **On event day:** the data build, benchmark generation, all baseline runs, fine-tuning and all results.
- **Data:** the Olist dataset is public (CC BY-NC-SA). The hand-written test questions were written by Kam on event day.

## Repo layout

```
config.yaml            model ids, prices, limits, setups (S0-S6 flags)
contracts.py           benchmark item, model output, agent response, eval row, run manifest
db/                    build_olist.py (CSV -> DuckDB), profile.py (integrity + trap evidence)
docs/                  olist_dictionary.md (schema + business rules given to the model)
bench/                 templates.py, generate.py, behavior.py, split.py, validate.py, handwritten.py, out/
agent/                 agent.py (harness + router), prompts.py, safety.py, checks.py
eval/                  run_eval.py, compare.py, stats.py, report.py, runs/, figures/, results.md, summary.json
train/                 build_sft_data.py, finetune.py, finetune.md, logs/
app/                   streamlit_app.py, audit_log.py
tests/                 test_compare.py, test_safety.py
```
