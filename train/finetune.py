"""LoRA SFT on Fireworks serverless training (CLAUDE.md 11).

Each example is rendered with the base model's chat template. Loss is on the
assistant tokens only ("</think>" + JSON + end token): the tuned model learns
to answer directly without a reasoning trace.

Usage: python train/finetune.py --dry-run   # tokenize + one forward pass on 2 examples
       python train/finetune.py             # full run; logs to train/logs/
"""
import argparse
import json
import math
import os
import random
import sys
import time
from pathlib import Path

import yaml
from dotenv import load_dotenv
from transformers import AutoTokenizer

from fireworks.training.sdk import AdamParams, FiretitanServiceClient, types

ROOT = Path(__file__).resolve().parents[1]
CFG = yaml.safe_load(open(ROOT / "config.yaml"))
load_dotenv(ROOT / ".env")

BASE_MODEL = CFG["models"]["small"]["id"]
TOKENIZER = CFG["training"]["tokenizer"]
HP = CFG["training"]
LOG_DIR = ROOT / "train" / "logs"


def load(name):
    return [json.loads(line) for line in open(ROOT / "train" / f"{name}.jsonl")]


def to_datum(tok, messages):
    prompt = tok.apply_chat_template(messages[:-1], tokenize=False, add_generation_prompt=True)
    full = tok.apply_chat_template(messages, tokenize=False) + tok.eos_token
    assert full.startswith(prompt), "chat template is not prefix-stable"
    p_ids = tok.encode(prompt, add_special_tokens=False)
    ids = tok.encode(full, add_special_tokens=False)
    assert ids[: len(p_ids)] == p_ids, "prompt tokens are not a prefix of the full sequence"
    weights = [0.0] * len(p_ids) + [1.0] * (len(ids) - len(p_ids))
    datum = types.Datum(model_input=types.ModelInput.from_ints(ids[:-1]),
                        loss_fn_inputs={"target_tokens": ids[1:], "weights": weights[1:]})
    return datum, len(ids), int(sum(weights))


def mean_loss(out, datums):
    """Per-token NLL from returned logprobs and weights (falls back to metrics)."""
    num = den = 0.0
    try:
        for o, d in zip(out.loss_fn_outputs, datums):
            lp = o["logprobs"].data
            w = d.loss_fn_inputs["weights"].data
            num -= sum(a * b for a, b in zip(lp, w))
            den += sum(w)
        return num / den
    except Exception:  # noqa: BLE001
        return out.metrics.get("loss:mean", out.metrics.get("loss:sum", float("nan")))


def log(f, **kw):
    kw["t"] = round(time.time(), 1)
    line = json.dumps(kw)
    print(line, flush=True)
    f.write(line + "\n")
    f.flush()


def main(dry_run=False):
    tok = AutoTokenizer.from_pretrained(TOKENIZER)
    train, val = load("sft_train"), load("sft_val")
    if dry_run:
        train, val = train[:2], val[:2]
    t_data = [to_datum(tok, ex["messages"]) for ex in train]
    v_data = [to_datum(tok, ex["messages"]) for ex in val]
    n_tok = sum(n for _, n, _ in t_data)
    print(f"train {len(t_data)} examples, {n_tok:,} tokens (~${n_tok / 1e6 * HP['price_per_m_tokens']:.2f}/epoch); "
          f"max len {max(n for _, n, _ in t_data)}; val {len(v_data)}")

    service = FiretitanServiceClient(api_key=os.environ["FIREWORKS_API_KEY"],
                                     base_url=CFG["fireworks"]["training_base_url"])
    tc = service.create_lora_training_client(base_model=BASE_MODEL, rank=HP["lora_rank"],
                                             alpha=HP["lora_alpha"], seed=CFG["seed"])
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    with open(LOG_DIR / f"run-{stamp}.jsonl", "w") as f:
        log(f, event="start", base_model=BASE_MODEL, hp=HP, n_train=len(t_data), n_val=len(v_data),
            session=getattr(service, "training_session_name", None))
        v_datums = [d for d, _, _ in v_data]

        def val_loss():
            return mean_loss(tc.forward(v_datums, "cross_entropy").result(), v_datums)

        log(f, event="val", step=0, val_loss=val_loss())
        if dry_run:
            log(f, event="dry_run_ok")
            return

        adam = AdamParams(learning_rate=HP["learning_rate"], beta1=0.9, beta2=0.95, eps=1e-8, weight_decay=0.0)
        bs = HP["batch_size"]
        order = list(range(len(t_data)))
        random.Random(CFG["seed"]).shuffle(order)
        steps = math.ceil(len(order) / bs) * HP["epochs"]
        step = 0
        for epoch in range(HP["epochs"]):
            for b in range(0, len(order), bs):
                batch = [t_data[i][0] for i in order[b:b + bs]]
                out = tc.forward_backward(batch, "cross_entropy").result()
                tc.optim_step(adam).result()
                step += 1
                log(f, event="train", step=step, of=steps, epoch=epoch, loss=mean_loss(out, batch))
                if step % HP["eval_every"] == 0 and step < steps:
                    log(f, event="val", step=step, val_loss=val_loss())
        log(f, event="val", step=step, val_loss=val_loss())
        path = tc.save_weights_for_sampler(HP["checkpoint_name"]).result().path
        log(f, event="saved", sampler_path=path, session=getattr(service, "training_session_name", None))
        print(f"\nSAMPLER PATH: {path}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    main(ap.parse_args().dry_run)
