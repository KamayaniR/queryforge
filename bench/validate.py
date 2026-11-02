"""Validate train/test: re-run every gold SQL, check leakage, print the mix."""
import difflib
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

import duckdb
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from bench.generate import is_degenerate, run  # noqa: E402
from contracts import BenchItem  # noqa: E402
from eval.compare import compare  # noqa: E402

CFG = yaml.safe_load(open(ROOT / "config.yaml"))
OUT = ROOT / CFG["paths"]["bench_out"]


def load(name):
    return [BenchItem(**json.loads(line)) for line in open(OUT / f"{name}.jsonl")]


def main():
    con = duckdb.connect(str(ROOT / CFG["paths"]["olist_db"]), read_only=True)
    train, test = load("train"), load("test")
    problems = 0

    # 1. Every gold SQL runs and reproduces its stored result.
    for it in train + test:
        if it.expected_action != "answer":
            assert it.gold_sql is None and it.gold_result is None, it.id
            continue
        try:
            _, rows = run(con, it.gold_sql)
        except Exception as e:  # noqa: BLE001
            print(f"ERROR {it.id}: {e}")
            problems += 1
            continue
        if is_degenerate(rows):
            print(f"DEGENERATE {it.id}")
            problems += 1
        elif not compare(it.gold_result, rows, it.order_matters)[0]:
            print(f"RESULT MISMATCH {it.id}")
            problems += 1

    # 2. Leakage: no (template, fill) or question text shared across splits; held-out templates absent from train.
    held = set(json.load(open(OUT / "heldout_templates.json")))
    fill_key = lambda it: it.id.rsplit("_", 1)[0]  # noqa: E731
    train_fills = {fill_key(it) for it in train if it.source == "template"}
    leak_fill = [it.id for it in test if it.source == "template" and fill_key(it) in train_fills]
    train_q = {it.question.strip().lower() for it in train}
    leak_q = [it.id for it in test if it.question.strip().lower() in train_q]
    leak_held = [it.id for it in train if it.template_id in held]
    leak_src = [it.id for it in train if it.source == "handwritten" or it.id.startswith("beh_test")]
    for name, ids in [("fill shared", leak_fill), ("question shared", leak_q),
                      ("held-out template in train", leak_held), ("test-only source in train", leak_src)]:
        print(f"leakage check: {name:28s} {len(ids)}")
        problems += len(ids)

    # 3. Near-duplicates: hand-written / behavior test questions vs train (flag only).
    train_texts = [it.question.lower() for it in train]
    for it in test:
        if it.source in ("handwritten", "behavior"):
            best = max(train_texts, key=lambda t: difflib.SequenceMatcher(None, t, it.question.lower()).ratio())
            r = difflib.SequenceMatcher(None, best, it.question.lower()).ratio()
            if r > 0.85:
                print(f"FLAG near-duplicate ({r:.2f}) {it.id}: {it.question!r} ~ {best!r}")

    # 4. Single-row zero/NULL results flagged for manual review are dropped in generate.py; report the mix.
    for name, rows in (("train", train), ("test", test)):
        print(f"\n== {name}: {len(rows)} items")
        for field in ("category", "source", "difficulty", "expected_action"):
            print(f"  {field:16s} {dict(sorted(Counter(getattr(r, field) for r in rows).items()))}")
    seen = Counter("unseen" if it.template_id in held else "seen" for it in test if it.source == "template")
    print(f"  test template items: {dict(seen)}")

    sha_file = OUT / "test.sha256"
    if sha_file.exists():
        ok = hashlib.sha256(open(OUT / "test.jsonl", "rb").read()).hexdigest() == sha_file.read_text().strip()
        print(f"\ntest.sha256 matches: {ok}")
        problems += 0 if ok else 1

    print(f"\n{'OK' if problems == 0 else f'{problems} PROBLEMS'}")
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
