"""Train/test split (CLAUDE.md section 8).

- ~25% of templates held out entirely (test only), stratified by category.
- Seen templates: disjoint fills in train and test (a fill never appears in both).
- Train fills are expanded to several phrasings; test uses one phrasing per fill.
- Test also gets behavior test items. Hand-written items are a separate frozen file (bench/handwritten.py).

Usage: python bench/split.py            # write train.jsonl + test.jsonl
       python bench/split.py --freeze   # also write test.sha256 (do this once, before the first baseline)
"""
import hashlib
import json
import random
import sys
from collections import defaultdict
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from bench import behavior  # noqa: E402
from contracts import BenchItem  # noqa: E402

CFG = yaml.safe_load(open(ROOT / "config.yaml"))
OUT = ROOT / CFG["paths"]["bench_out"]
HELDOUT_FRAC = 0.25
TEST_FILLS_SEEN = 12
TEST_FILLS_HELDOUT = 14
TRAIN_PHRASINGS = 3
TRAIN_CAP_PER_TEMPLATE = 45


def pick_heldout(pool, rng):
    by_cat = defaultdict(set)
    for r in pool:
        by_cat[r["category"]].add(r["template_id"])
    total = round(HELDOUT_FRAC * sum(len(v) for v in by_cat.values()))
    quota = {c: int(len(v) * HELDOUT_FRAC) for c, v in by_cat.items()}
    rema = sorted(by_cat, key=lambda c: (-(len(by_cat[c]) * HELDOUT_FRAC % 1), rng.random()))
    for c in rema[: total - sum(quota.values())]:
        quota[c] += 1
    held = set()
    for c in sorted(by_cat):
        held |= set(rng.sample(sorted(by_cat[c]), quota[c]))
    return held


def item(r, question, split, k):
    return BenchItem(
        id=f"{r['template_id']}_{r['fill_index']:04d}_{k}", question=question,
        category=r["category"], difficulty=r["difficulty"], source="template",
        template_id=r["template_id"], split=split, expected_action="answer",
        gold_sql=r["gold_sql"], gold_columns=r["gold_columns"], gold_result=r["gold_result"],
        order_matters=r["order_matters"],
        notes=json.dumps({"explanation": r["explanation"], "assumptions": r["assumptions"]}),
    ).model_dump()


def main(freeze=False):
    rng = random.Random(CFG["seed"])
    pool = [json.loads(line) for line in open(OUT / "pool.jsonl")]
    held = pick_heldout(pool, rng)
    by_t = defaultdict(list)
    for r in pool:
        by_t[r["template_id"]].append(r)

    train, test = [], []
    for tid in sorted(by_t):
        fills = by_t[tid][:]
        rng.shuffle(fills)
        if tid in held:
            for r in fills[:TEST_FILLS_HELDOUT]:
                k = rng.randrange(len(r["questions"]))
                test.append(item(r, r["questions"][k], "test", k))
            continue
        n_test = min(TEST_FILLS_SEEN, max(1, len(fills) // 3))
        for r in fills[:n_test]:
            k = rng.randrange(len(r["questions"]))
            test.append(item(r, r["questions"][k], "test", k))
        t_items = []
        for r in fills[n_test:]:
            ks = rng.sample(range(len(r["questions"])), min(TRAIN_PHRASINGS, len(r["questions"])))
            t_items += [item(r, r["questions"][k], "train", k) for k in ks]
        rng.shuffle(t_items)
        train += t_items[:TRAIN_CAP_PER_TEMPLATE]

    train += behavior.items("train")
    test += behavior.items("test")

    # Hand-written items live in their own frozen file (bench/out/test_handwritten.jsonl), built by
    # bench/handwritten.py, so template baselines can start before they are written.

    rng.shuffle(train)
    for name, rows in (("train", train), ("test", test)):
        with open(OUT / f"{name}.jsonl", "w") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")
    json.dump(sorted(held), open(OUT / "heldout_templates.json", "w"), indent=1)

    print(f"held-out templates ({len(held)}): {sorted(held)}")
    print(f"train {len(train)}  test {len(test)}")
    if freeze:
        sha = hashlib.sha256(open(OUT / "test.jsonl", "rb").read()).hexdigest()
        (OUT / "test.sha256").write_text(sha + "\n")
        print(f"FROZEN test.jsonl sha256={sha}")


if __name__ == "__main__":
    if "--freeze" in sys.argv and (OUT / "test.sha256").exists():
        sys.exit("test.sha256 already exists: the test set is frozen. Delete it only with Kam's approval.")
    main(freeze="--freeze" in sys.argv)
