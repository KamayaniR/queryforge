"""Expand templates into (template, fill) instances, run every gold SQL, keep valid ones.

Writes bench/out/pool.jsonl: one record per instance with all rendered phrasings.
split.py later picks phrasings and assigns train/test.
"""
import datetime as dt
import decimal
import json
import sys
from pathlib import Path

import duckdb
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from bench.templates import TEMPLATES  # noqa: E402

CFG = yaml.safe_load(open(ROOT / "config.yaml"))
OUT = ROOT / CFG["paths"]["bench_out"]


def jsonable(v):
    if isinstance(v, decimal.Decimal):
        return float(v)
    if isinstance(v, (dt.date, dt.datetime)):
        return v.isoformat()
    return v


def run(con, sql):
    cur = con.execute(sql)
    cols = [d[0] for d in cur.description]
    rows = [[jsonable(v) for v in r] for r in cur.fetchall()]
    return cols, rows


def is_degenerate(rows):
    """Empty, or a single cell that is NULL or zero."""
    if not rows:
        return True
    return len(rows) == 1 and len(rows[0]) == 1 and rows[0][0] in (None, 0, 0.0)


def main():
    con = duckdb.connect(str(ROOT / CFG["paths"]["olist_db"]), read_only=True)
    OUT.mkdir(parents=True, exist_ok=True)
    kept, dropped = [], {}
    for t in TEMPLATES:
        for k, fill in enumerate(t.fills):
            fmt = dict(fill)
            if t.n_key:
                fmt.update(_m="", _lim=fill[t.n_key])
            sql = t.sql.format(**fmt)
            reason = None
            try:
                cols, rows = run(con, sql)
                if is_degenerate(rows):
                    reason = "degenerate"
                elif any(None in r for r in rows):
                    reason = "null_in_result"
                elif t.n_key:
                    n = fill[t.n_key]
                    tie_sql = t.sql.format(**{**fill, "_m": f", {t.tie_metric} AS _metric", "_lim": n + 1})
                    _, tie_rows = run(con, tie_sql)
                    if len(rows) < n:
                        reason = "fewer_than_n"
                    elif len(tie_rows) > n and tie_rows[n - 1][-1] == tie_rows[n][-1]:
                        reason = "tie_at_cutoff"
            except Exception as e:  # noqa: BLE001
                reason = f"error: {e}"
            if reason:
                dropped.setdefault(t.id, []).append(reason)
                continue
            kept.append({
                "template_id": t.id, "fill_index": k, "category": t.category, "difficulty": t.difficulty,
                "questions": [p.format(**fill) for p in t.phrasings],
                "gold_sql": sql, "gold_columns": cols, "gold_result": rows,
                "order_matters": t.order_matters,
                "explanation": t.explain.format(**fill),
                "assumptions": t.assumptions,
            })
    with open(OUT / "pool.jsonl", "w") as f:
        for r in kept:
            f.write(json.dumps(r) + "\n")

    print(f"kept {len(kept)} instances from {len(TEMPLATES)} templates")
    per = {}
    for r in kept:
        per[r["template_id"]] = per.get(r["template_id"], 0) + 1
    for t in TEMPLATES:
        d = dropped.get(t.id, [])
        reasons = sorted(set(x if not x.startswith("error") else x[:120] for x in d))
        print(f"  {t.id:30s} {t.category:14s} kept {per.get(t.id, 0):3d} dropped {len(d):3d} {reasons if d else ''}")


if __name__ == "__main__":
    main()
