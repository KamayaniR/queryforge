"""Result sanity checks for the harness (S4+). Return a list of human-readable warnings."""
import re

_RATE_COL = re.compile(r"(rate|share|ratio|fraction|pct|percent)", re.I)
_SIGNED_Q = re.compile(r"(growth|change|difference|delta|vs|versus|compare|increase|decrease|drop)", re.I)
_SINGLE_Q = re.compile(r"^\s*(how many|what('s| is| was)? (the )?(total|average|avg|number|count|sum|share|rate))", re.I)
_MULTI_Q = re.compile(r"\b(by|per|each|breakdown|top|which|list|monthly|month-by-month|trend)\b", re.I)


def sanity(question: str, columns: list[str], rows: list[list]) -> list[str]:
    warnings = []
    if not rows:
        return ["The query returned no rows. Check filters (status spelling, category names, date ranges)."]
    if all(v is None for r in rows for v in r):
        warnings.append("The query returned only NULL values. Check joins and filters.")
    pct = "%" in question or "percent" in question.lower()
    for j, col in enumerate(columns):
        vals = [r[j] for r in rows if isinstance(r[j], (int, float)) and not isinstance(r[j], bool)]
        if not vals:
            continue
        if _RATE_COL.search(col or ""):
            hi = 100 if pct else 1
            if any(v < 0 or v > hi for v in vals):
                warnings.append(f"Column '{col}' looks like a rate but has values outside [0, {hi}].")
        if any(v < 0 for v in vals) and not _SIGNED_Q.search(question):
            warnings.append(f"Column '{col}' has negative values, which is unexpected for counts or amounts.")
    if len(rows) > 1 and _SINGLE_Q.search(question) and not _MULTI_Q.search(question):
        warnings.append(f"The question asks for a single number but the query returned {len(rows)} rows.")
    if len(rows) >= 1000:
        warnings.append("The query returned 1000+ rows; an aggregate is probably expected.")
    return warnings
