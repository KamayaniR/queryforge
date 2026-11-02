# Fine-tuning record (event day, 2026-11-02)

## What was trained
- **Base model:** `accounts/fireworks/models/glm-5p3-flash` (GLM 5.3 Flash, 320B MoE). It's the same model as the S1 baseline.
- **Method:** LoRA SFT on Fireworks **serverless training** (`https://api.fireworks.ai/training/v1/serverless`), `fireworks-ai[training]==1.2.30`
- **Settings** (organizers' sample): rank 16, alpha 32, lr 1e-4 (Adam β=(0.9, 0.95), eps 1e-8, no weight decay), batch 16, 1 epoch, seed 42
- **Data:** `bench/out/train.jsonl`, train split only.
  - 1,230 template items (31 seen templates) plus 120 clarify/refuse items from a separate train-only behavior set.
  - 5% (67 examples) was held out for validation loss, leaving 1,283 training examples (2.10M tokens, about $18.7 at $8.89 per 1M).
- **Example format** (`train/build_sft_data.py`):
  - system = the exact S1 system prompt (instructions + data dictionary)
  - user = ticket text
  - assistant = contract 5.4 JSON with the gold SQL, a short explanation and assumptions
- **Tokenization** (`train/finetune.py`):
  - Rendered with the base model's chat template (`zai-org/GLM-5.3-Flash`), plus the end-of-sequence token.
  - Loss is on assistant tokens only. The template opens the assistant turn with `<think>`, so the target is `</think>{json}`: **the tuned model learns to answer without a reasoning trace**.
- **Excluded:** no test, hand-written or test-behavior item is in the training data. `bench/validate.py` checks this.

## Commands run
```bash
python bench/generate.py && python bench/split.py && python bench/validate.py
python train/build_sft_data.py          # -> train/sft_train.jsonl (1283), train/sft_val.jsonl (67)
python train/finetune.py --dry-run      # tokenize + one forward pass on 2 examples (session deleted afterwards)
python train/finetune.py                # full run, log: train/logs/run-*.jsonl and finetune_stdout.log
```

## Outcome
- 81 steps, about 45 s per step, roughly 75 minutes wall clock.
- Validation loss (per assistant token):

  | Step | 0 | 20 | 40 | 60 | 80 | 81 |
  |---|---|---|---|---|---|---|
  | Val loss | 0.822 | 0.044 | 0.022 | 0.016 | 0.012 | 0.012 |

  It decreased monotonically, so there's no sign of overfitting on held-out train-distribution examples.
- Sampler snapshot: `kamayanirai78-jyb1te/run-a3628634fb844ad4a9fade93b0bd61c4/qf-tuned-cce4bcb8`
- Promoted to a model: `accounts/kamayanirai78-jyb1te/models/queryforge-glm-flash-lora` (HF_PEFT_ADDON, READY)

## Serving
- **Eval (S5/S5H):** the serverless sampling client (`create_sampling_client(model_path=<snapshot>)`). The agent renders the same chat messages with the base tokenizer's template, so S5 sees exactly the S1 prompt. No deployment is needed.
  - The first calls in each process include a ~4 minute cold start (loading the snapshot). It is not removed: it lands in those items' latency, which inflates S5 p95.
  - S5 latency is measured on this route, which is not the production chat endpoint. See the README caveats.
- **Production:** a promoted LoRA is not served on the shared serverless chat endpoint (it returns 404). Deploy it with live merge:
  ```bash
  firectl deployment create "accounts/kamayanirai78-jyb1te/models/queryforge-glm-flash-lora" --deployment-shape default
  ```
  Then set `models.tuned.id` to that model, with `backend: chat`.
- **Cost assumption:** tuned-model cost uses the base model's serverless price ($0.15 / $0.50 per 1M tokens). A dedicated deployment is billed per GPU-hour instead.
