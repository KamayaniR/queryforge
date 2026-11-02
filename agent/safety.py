"""Safety: ticket pre-filter (harness only) and SQL checks (all setups). CLAUDE.md section 9."""
import re

import sqlglot
from sqlglot import exp

# ---- Pre-filter (S4+): cheap pattern checks on the ticket text before any model call.
_PREFILTER = [
    ("write", r"\b(delete|drop|truncate|insert|update|alter|merge|rename|wipe|grant|revoke)\b\s+"
              r"(from|table|into|the|all|column|database|view|records?|orders?|payments?|reviews?|customers?|sellers?|products?)\b"),
    ("write", r"\b(set|mark|change)\b.{0,40}\b(status|price|value)s?\b.{0,20}\bto\b"),
    ("write", r"\bcreate\s+(a\s+)?(backup\s+)?(table|view|index)\b"),
    ("write", r"^\W*(please\s+|pls\s+|can you\s+)?(set|mark|change|update|edit|modify|fix|correct)\b.{0,60}\bto\b"),
    ("injection", r";\s*(drop|delete|insert|update|alter|truncate|create|attach|copy|pragma)\b"),
    ("injection", r"\b(ignore|disregard|forget)\b.{0,30}\b(instructions|rules|prompt)\b"),
    ("injection", r"\b(developer|admin|god)\s+mode\b|\bsystem prompt\b"),
    ("injection", r"\b(pragma|attach)\b"),
    ("pii", r"\b(phone|e-?mail|cpf|rg number|home address|street|passport|card numbers?|card details|full name|names and)\b"),
    ("out_of_scope", r"\b(password|vpn|weather|poem|joke|stock price|exchange rate|world cup|meeting|schedule)\b"),
]
_REASONS = {
    "write": "I can only read data. Requests to change, delete or create data are not allowed.",
    "injection": "This request contains instructions or SQL commands I can't run. I only run single read-only SELECT queries.",
    "pii": "Personal data such as names, contact details or IDs is not in the database and cannot be shared.",
    "out_of_scope": "That's not a question about the Olist data, so I can't answer it.",
}


def prefilter(text: str) -> str | None:
    """Return a refusal reason if the ticket should be refused without a model call."""
    t = text.lower()
    for kind, pat in _PREFILTER:
        if re.search(pat, t):
            return _REASONS[kind]
    return None


# ---- SQL checks (all setups).
_BLOCKED_NODES = tuple(getattr(exp, n) for n in (
    "Insert", "Update", "Delete", "Drop", "Create", "Alter", "Merge", "TruncateTable", "Command",
    "Copy", "Attach", "Detach", "Pragma", "Set", "Use", "Transaction", "Commit", "Rollback", "LoadData",
    "Grant", "Revoke") if hasattr(exp, n))
_BLOCKED_FUNC = re.compile(r"^(read_\w+|glob|query|query_table|getenv|sniff_csv|parquet_\w+|duckdb_\w+|pragma_\w+|"
                           r"current_setting|load|install|system)$", re.I)


class UnsafeSQL(Exception):
    pass


def check_sql(sql: str, allowed_tables: set[str], dialect: str = "duckdb", row_limit: int = 1000) -> str:
    """Validate a single read-only SELECT. Returns the SQL to execute (with LIMIT added if needed)."""
    if not sql or not sql.strip():
        raise UnsafeSQL("empty SQL")
    try:
        stmts = [s for s in sqlglot.parse(sql, read=dialect) if s is not None]
    except sqlglot.errors.ParseError as e:
        raise SyntaxError(str(e).splitlines()[0]) from e
    if len(stmts) != 1:
        raise UnsafeSQL(f"expected exactly one statement, got {len(stmts)}")
    tree = stmts[0]
    if not isinstance(tree, (exp.Select, exp.SetOperation)):
        raise UnsafeSQL(f"only SELECT queries are allowed, got {type(tree).__name__}")
    for node in tree.walk():
        if isinstance(node, _BLOCKED_NODES):
            raise UnsafeSQL(f"blocked statement type {type(node).__name__}")
        if isinstance(node, (exp.Anonymous, exp.Func)):
            name = node.name if isinstance(node, exp.Anonymous) else node.sql_name()
            if name and _BLOCKED_FUNC.match(name):
                raise UnsafeSQL(f"blocked function {name}")
    ctes = {c.alias_or_name.lower() for c in tree.find_all(exp.CTE)}
    for t in tree.find_all(exp.Table):
        name = t.name.lower()
        if not name:
            continue  # table functions such as unnest/range
        if name not in allowed_tables and name not in ctes:
            raise UnsafeSQL(f"unknown or disallowed table '{t.name}'")
    has_agg = tree.find(exp.AggFunc) is not None
    if not tree.args.get("limit") and not has_agg:
        return f"SELECT * FROM ({sql.strip().rstrip(';')}) AS _q LIMIT {row_limit}"
    return sql.strip().rstrip(";")
