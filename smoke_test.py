"""Step 0: list Fireworks serverless models and make one call each to the small and large model."""
import os
import sys
import time

import yaml
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()
cfg = yaml.safe_load(open("config.yaml"))
key = os.environ.get("FIREWORKS_API_KEY")
if not key:
    sys.exit("FIREWORKS_API_KEY missing: put it in queryforge/.env")

client = OpenAI(api_key=key, base_url=cfg["fireworks"]["inference_base_url"])

print("== Serverless models matching nemotron / glm / qwen / muse")
ids = sorted(m.id for m in client.models.list())
for mid in ids:
    if any(k in mid.lower() for k in ("nemotron", "glm", "qwen", "muse")):
        print("  ", mid)
print(f"({len(ids)} models total)")

PROMPT = 'Return only JSON: {"sql": "<a DuckDB query counting rows in table orders>"}'
for role in ("small", "large"):
    model = cfg["models"][role]["id"]
    if len(sys.argv) > 1 and role == "small":
        model = sys.argv[1]  # try alternative small model: python smoke_test.py <model_id>
    t0 = time.time()
    try:
        r = client.chat.completions.create(
            model=model, temperature=0, max_tokens=512,
            messages=[{"role": "user", "content": PROMPT}],
        )
        msg = r.choices[0].message
        reasoning = getattr(msg, "reasoning_content", None)
        print(f"\n== {role}: {model}")
        print(f"latency {time.time() - t0:.2f}s | in {r.usage.prompt_tokens} out {r.usage.completion_tokens}"
              f" | reasoning trace: {'yes' if reasoning else 'no'}")
        print("content:", (msg.content or "")[:300])
    except Exception as e:
        print(f"\n== {role}: {model} FAILED: {e}")
