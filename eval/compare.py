"""Result-set comparison (CLAUDE.md 10.1).

Rows are compared as tuples, ignoring column names. Row order is ignored unless
order_matters. Numbers are compared with a tolerance: rates (|gold| <= 1) to
3 decimals, other values to 2 decimals (DuckDB float sums are not bit-stable).
Extra predicted columns are allowed if some subset of them reproduces every gold
column: that is a "partial" match and counts as correct.
"""
import datetime as dt
import decimal
from itertools import permutations

MAX_PRED_COLS = 8


def norm(v):
    if isinstance(v, bool):
        return int(v)
    if isinstance(v, decimal.Decimal):
        return float(v)
    if isinstance(v, dt.datetime):
        return v.date().isoformat() if v.time() == dt.time() else v.isoformat()
    if isinstance(v, dt.date):
        return v.isoformat()
    if isinstance(v, str):
        s = v.strip()
        if s.endswith("T00:00:00") or s.endswith(" 00:00:00"):
            s = s[:10]
        return s
    return v


def _num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def cell_eq(gold, pred):
    g, p = norm(gold), norm(pred)
    if g is None or p is None:
        return g is None and p is None
    if _num(g) and _num(p):
        tol = 5e-4 if abs(g) <= 1 else 0.01
        return abs(g - p) <= max(tol, 1e-6 * abs(g))
    if _num(g) or _num(p):
        return False
    return str(g).lower() == str(p).lower()


def _rows_eq(gold_rows, pred_rows, order_matters):
    if len(gold_rows) != len(pred_rows):
        return False
    if order_matters:
        return all(all(cell_eq(g, p) for g, p in zip(gr, pr)) for gr, pr in zip(gold_rows, pred_rows))
    used = [False] * len(pred_rows)
    for gr in gold_rows:
        for j, pr in enumerate(pred_rows):
            if not used[j] and all(cell_eq(g, p) for g, p in zip(gr, pr)):
                used[j] = True
                break
        else:
            return False
    return True


def compare(gold_rows, pred_rows, order_matters=False):
    """Return (correct, match_type) with match_type in {"exact", "partial", "none"}."""
    gold_rows = [list(r) for r in gold_rows or []]
    pred_rows = [list(r) for r in pred_rows or []]
    if not gold_rows or not pred_rows:
        return (not gold_rows and not pred_rows), ("exact" if not gold_rows and not pred_rows else "none")
    k, m = len(gold_rows[0]), len(pred_rows[0])
    if m < k or m > MAX_PRED_COLS:
        return False, "none"
    # Try the identity mapping first, then any injective mapping gold col -> pred col.
    mappings = [tuple(range(k))] + [p for p in permutations(range(m), k) if p != tuple(range(k))]
    for mp in mappings:
        projected = [[r[i] for i in mp] for r in pred_rows]
        if _rows_eq(gold_rows, projected, order_matters):
            return True, ("exact" if m == k else "partial")
    return False, "none"
