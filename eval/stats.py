"""Paired significance vs the S1 baseline (CLAUDE.md 10.3).

- McNemar (exact binomial) on items where exactly one of the two setups is right.
- Cluster bootstrap (templates are clusters; hand-written/behavior items are their
  own cluster), 5,000 resamples, 95% interval of the accuracy gap. Cost and
  latency gaps are bootstrapped the same way.
A gain is "real" only if p < 0.05 and the interval excludes zero.
"""
import json
from collections import defaultdict
from pathlib import Path

import numpy as np
import yaml
from scipy.stats import binomtest

ROOT = Path(__file__).resolve().parents[1]
CFG = yaml.safe_load(open(ROOT / "config.yaml"))
RUNS = ROOT / CFG["paths"]["runs"]
N_BOOT = 5000


def load_run(run_ids):
    """Load one run id or a list of run ids (e.g. test + hand-written) merged by item_id."""
    out = {}
    for run_id in [run_ids] if isinstance(run_ids, str) else run_ids:
        path = RUNS / run_id / "results.jsonl"
        if not path.exists():
            return None
        out.update({r["item_id"]: r for r in map(json.loads, open(path))})
    return out


def mcnemar(base, new):
    only_new = sum(1 for b, n in zip(base, new) if n and not b)
    only_base = sum(1 for b, n in zip(base, new) if b and not n)
    k = only_new + only_base
    p = binomtest(min(only_new, only_base), k, 0.5).pvalue if k else 1.0
    return only_new, only_base, float(p)


def cluster_bootstrap(clusters, base_vals, new_vals, seed):
    """95% CI of mean(new) - mean(base), resampling clusters with replacement."""
    by = defaultdict(list)
    for i, c in enumerate(clusters):
        by[c].append(i)
    groups = list(by.values())
    b = np.asarray(base_vals, float)
    n = np.asarray(new_vals, float)
    sums_b = np.array([b[g].sum() for g in groups])
    sums_n = np.array([n[g].sum() for g in groups])
    sizes = np.array([len(g) for g in groups])
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(groups), size=(N_BOOT, len(groups)))
    gaps = (sums_n[idx].sum(1) - sums_b[idx].sum(1)) / sizes[idx].sum(1)
    lo, hi = np.percentile(gaps, [2.5, 97.5])
    return float(n.mean() - b.mean()), float(lo), float(hi)


def compare_runs(base_run, new_run, subset=lambda r: True):
    base, new = load_run(base_run), load_run(new_run)
    if not base or not new:
        return None
    ids = sorted(i for i in base if i in new and subset(base[i]))
    if not ids:
        return None
    clusters = [base[i]["cluster"] for i in ids]
    b_ok = [base[i]["correct"] for i in ids]
    n_ok = [new[i]["correct"] for i in ids]
    only_new, only_base, p = mcnemar(b_ok, n_ok)
    gap, lo, hi = cluster_bootstrap(clusters, b_ok, n_ok, CFG["seed"])
    c_gap = cluster_bootstrap(clusters, [base[i]["cost_usd"] * 1000 for i in ids],
                              [new[i]["cost_usd"] * 1000 for i in ids], CFG["seed"])
    l_gap = cluster_bootstrap(clusters, [base[i]["latency_ms"] for i in ids],
                              [new[i]["latency_ms"] for i in ids], CFG["seed"])
    real = p < 0.05 and (lo > 0 or hi < 0)
    verdict = ("real gain" if gap > 0 else "real loss") if real else "could be luck"
    return {
        "n": len(ids), "base_acc": float(np.mean(b_ok)), "new_acc": float(np.mean(n_ok)),
        "gap": gap, "ci95": [lo, hi], "only_new_right": only_new, "only_base_right": only_base,
        "p_value": p, "verdict": verdict,
        "cost_per_1k_gap": {"gap": c_gap[0], "ci95": [c_gap[1], c_gap[2]]},
        "latency_ms_gap": {"gap": l_gap[0], "ci95": [l_gap[1], l_gap[2]]},
    }


if __name__ == "__main__":
    import sys
    base, new = sys.argv[1], sys.argv[2]
    for name, sub in [("answer items", lambda r: r["expected_action"] == "answer"), ("all items", lambda r: True)]:
        print(name, json.dumps(compare_runs(base, new, sub), indent=1))
