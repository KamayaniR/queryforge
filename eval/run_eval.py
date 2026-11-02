"""Run one setup over the test set and score it (CLAUDE.md 10).

Writes eval/runs/{run_id}/manifest.json and results.jsonl (one EvalRow per item).
Re-running with the same --run-id resumes: finished items are skipped.

Usage: python eval/run_eval.py --setup S1 [--limit 10] [--run-id ID] [--allow-unfrozen]
"""
import argparse
import hashlib
import json
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from agent import agent, prompts  # noqa: E402
from contracts import BenchItem, EvalRow, RunManifest  # noqa: E402
from eval.compare import compare  # noqa: E402

CFG = yaml.safe_load(open(ROOT / "config.yaml"))
BENCH = ROOT / CFG["paths"]["bench_out"]


def git_commit():
    try:
        sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, stderr=subprocess.DEVNULL).decode().strip()
        dirty = subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT).decode().strip()
        return sha + ("-dirty" if dirty else "")
    except Exception:  # noqa: BLE001
        return "uncommitted"


def score(it: BenchItem, resp, run_id, setup, held) -> EvalRow:
    pred = resp.action
    correct, match = False, "none"
    failure = None
    if it.expected_action == "answer":
        if pred == "answer" and not resp.error:
            correct, match = compare(it.gold_result, resp.rows, it.order_matters)
            failure = None if correct else "wrong_result"
        elif pred == "escalate":
            failure = "escalated"
        elif pred == "answer":
            failure = resp.error.split(":", 1)[0]
        else:
            failure = "wrong_action"
    else:
        correct = pred == it.expected_action
        match = "exact" if correct else "none"
        failure = None if correct else ("escalated" if pred == "escalate" else
                                        "invalid_output" if (resp.error or "").startswith("invalid_output") else "wrong_action")
    return EvalRow(
        run_id=run_id, item_id=it.id, setup=setup, category=it.category, difficulty=it.difficulty, source=it.source,
        template_id=it.template_id, cluster=it.template_id if it.source == "template" else it.id,
        seen_template=(it.template_id not in held) if it.source == "template" else None,
        expected_action=it.expected_action, predicted_action=pred, correct=correct, match_type=match,
        failure_type=failure, latency_ms=resp.latency_ms, input_tokens=resp.input_tokens,
        output_tokens=resp.output_tokens, cost_usd=resp.cost_usd, pred_sql=resp.sql, error=resp.error,
    )


def summarize(rows):
    ans = [r for r in rows if r["expected_action"] == "answer"]
    beh = [r for r in rows if r["expected_action"] != "answer"]
    lat = [r["latency_ms"] for r in rows]
    cost = sum(r["cost_usd"] for r in rows)
    return {
        "n": len(rows),
        "exec_accuracy": round(float(np.mean([r["correct"] for r in ans])), 4) if ans else None,
        "behavior_accuracy": round(float(np.mean([r["correct"] for r in beh])), 4) if beh else None,
        "false_clarify_rate": round(float(np.mean([r["predicted_action"] == "clarify" for r in ans])), 4) if ans else None,
        "p50_latency_ms": int(np.percentile(lat, 50)) if lat else None,
        "p95_latency_ms": int(np.percentile(lat, 95)) if lat else None,
        "cost_usd": round(cost, 4),
        "cost_per_1k": round(cost / len(rows) * 1000, 4) if rows else None,
        "failures": {k: sum(1 for r in rows if r["failure_type"] == k)
                     for k in sorted({r["failure_type"] for r in rows if r["failure_type"]})},
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--setup", required=True)
    ap.add_argument("--limit", type=int)
    ap.add_argument("--run-id")
    ap.add_argument("--split", default="test", choices=["test", "test_handwritten"])
    ap.add_argument("--allow-unfrozen", action="store_true", help="dev runs before the test set is frozen")
    args = ap.parse_args()

    test_bytes = open(BENCH / f"{args.split}.jsonl", "rb").read()
    sha = hashlib.sha256(test_bytes).hexdigest()
    frozen = BENCH / f"{args.split}.sha256"
    if frozen.exists():
        assert frozen.read_text().strip() == sha, "test.jsonl does not match frozen test.sha256"
    elif not args.allow_unfrozen:
        sys.exit("Test set not frozen. Run bench/split.py --freeze first, or pass --allow-unfrozen for a dev run.")

    items = [BenchItem(**json.loads(line)) for line in test_bytes.decode().splitlines() if line.strip()]
    if args.limit:
        items = items[: args.limit]
    held = set(json.load(open(BENCH / "heldout_templates.json")))
    s = CFG["setups"][args.setup]
    run_id = args.run_id or f"{args.setup}_{time.strftime('%Y%m%d-%H%M%S')}"
    out_dir = ROOT / CFG["paths"]["runs"] / run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    res_path = out_dir / "results.jsonl"
    done = {json.loads(line)["item_id"] for line in open(res_path)} if res_path.exists() else set()

    model_key = s["model"]
    manifest = RunManifest(
        run_id=run_id, timestamp=time.strftime("%Y-%m-%dT%H:%M:%S"), setup=args.setup,
        model_id=CFG["models"][model_key]["id"] if not s.get("router") else
        f"{CFG['models'][CFG['setups'][s['base']]['model']]['id']} -> {CFG['models'][CFG['setups'][s['escalate_to']]['model']]['id']}",
        temperature=CFG["generation"]["temperature"], max_tokens=CFG["generation"]["max_tokens"],
        harness_flags={**s, "max_sql_retries": CFG["limits"]["max_sql_retries"], "sql_timeout_s": CFG["limits"]["sql_timeout_s"]},
        system_prompt=prompts.system_prompt(dictionary=s["dictionary"],
                                            sample_values=agent.SAMPLE_VALUES if s["harness"] else None),
        test_file_sha256=sha, git_commit=git_commit(), item_count=len(items),
    )
    (out_dir / "manifest.json").write_text(manifest.model_dump_json(indent=1))

    todo = [it for it in items if it.id not in done]
    budget = CFG["limits"]["budget_usd_per_run"]
    spent = 0.0
    lock = threading.Lock()
    print(f"{run_id}: {len(todo)} to run ({len(done)} already done), budget ${budget}")
    t0 = time.time()
    with ThreadPoolExecutor(CFG["limits"]["max_concurrency"]) as pool, open(res_path, "a") as f:
        futs = {}
        for it in todo:
            futs[pool.submit(agent.answer, it.question, args.setup)] = it
        for k, fut in enumerate(as_completed(futs), 1):
            it = futs[fut]
            row = score(it, fut.result(), run_id, args.setup, held)
            with lock:
                spent += row.cost_usd
                f.write(row.model_dump_json() + "\n")
                f.flush()
            if k % 25 == 0 or k == len(todo):
                print(f"  {k}/{len(todo)}  ${spent:.3f}  {time.time() - t0:.0f}s", flush=True)
            if spent > budget:
                print(f"BUDGET EXCEEDED (${spent:.2f}); cancelling remaining items")
                for fu in futs:
                    fu.cancel()
                break

    rows = [json.loads(line) for line in open(res_path)]
    summ = summarize(rows)
    (out_dir / "summary.json").write_text(json.dumps(summ, indent=1))
    print(json.dumps(summ, indent=1))


if __name__ == "__main__":
    main()
