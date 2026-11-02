"""bench/out/train.jsonl -> train/sft_{train,val}.jsonl chat examples (CLAUDE.md 11).

system = the exact S1 prompt; user = question; assistant = contracts 5.4 JSON.
Only the train split is read; 5% is held out for validation loss.
"""
import json
import random
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from agent.prompts import assistant_json, system_prompt  # noqa: E402
from contracts import BenchItem  # noqa: E402

CFG = yaml.safe_load(open(ROOT / "config.yaml"))
VAL_FRAC = 0.05


def to_example(it: BenchItem, system: str) -> dict:
    if it.expected_action == "answer":
        meta = json.loads(it.notes)
        reply = assistant_json("answer", sql=it.gold_sql, explanation=meta["explanation"],
                               assumptions=meta["assumptions"])
    elif it.expected_action == "clarify":
        reply = assistant_json("clarify", clarifying_question=it.notes)
    else:
        reply = assistant_json("refuse", refusal_reason=it.notes)
    return {"id": it.id, "messages": [{"role": "system", "content": system},
                                      {"role": "user", "content": it.question},
                                      {"role": "assistant", "content": reply}]}


def main():
    items = [BenchItem(**json.loads(line)) for line in open(ROOT / CFG["paths"]["bench_out"] / "train.jsonl")]
    assert all(it.split == "train" and it.source != "handwritten" for it in items), "non-train item in train.jsonl"
    system = system_prompt(dictionary=True)
    examples = [to_example(it, system) for it in items]
    random.Random(CFG["seed"]).shuffle(examples)
    n_val = int(len(examples) * VAL_FRAC)
    for name, rows in (("sft_val", examples[:n_val]), ("sft_train", examples[n_val:])):
        with open(ROOT / "train" / f"{name}.jsonl", "w") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")
        print(f"{name}: {len(rows)} examples")


if __name__ == "__main__":
    main()
