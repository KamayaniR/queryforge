"""Shared data contracts (CLAUDE.md section 5). Do not change without Kam's approval."""
from typing import Any, Literal

from pydantic import BaseModel, Field

Category = Literal["simple", "join", "date", "business_rule", "gotcha", "clarify", "refuse"]
Difficulty = Literal["easy", "medium", "hard"]
Source = Literal["template", "handwritten", "behavior"]
Action = Literal["answer", "clarify", "refuse"]
FailureType = Literal[
    "syntax_error", "runtime_error", "wrong_result", "timeout", "safety_blocked",
    "wrong_action", "invalid_output", "escalated",
]


class BenchItem(BaseModel):
    """5.1 Benchmark item, one per jsonl line."""
    id: str
    db: str = "olist"
    dialect: str = "duckdb"
    question: str
    category: Category
    difficulty: Difficulty
    source: Source
    template_id: str | None = None
    split: Literal["train", "test"]
    expected_action: Action
    gold_sql: str | None = None
    gold_columns: list[str] | None = None
    gold_result: list[list[Any]] | None = None
    order_matters: bool = False
    notes: str = ""


class ModelOutput(BaseModel):
    """5.4 JSON the LLM returns."""
    action: Action
    sql: str | None = None
    explanation: str | None = None
    assumptions: list[str] = Field(default_factory=list)
    clarifying_question: str | None = None
    refusal_reason: str | None = None


class AgentResponse(BaseModel):
    """5.3 What answer() returns. Never raised; errors go in `error`."""
    action: Literal["answer", "clarify", "refuse", "escalate"]
    sql: str | None = None
    columns: list[str] | None = None
    rows: list[list[Any]] | None = None  # max 1000
    explanation: str | None = None
    assumptions: list[str] = Field(default_factory=list)
    clarifying_question: str | None = None
    refusal_reason: str | None = None
    confidence: Literal["high", "low"] = "high"
    model_used: str = ""
    attempts: int = 0
    routed: bool = False
    latency_ms: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    error: str | None = None


class EvalRow(BaseModel):
    """5.5 Eval result row."""
    run_id: str
    item_id: str
    setup: str
    category: str
    difficulty: str
    source: str
    template_id: str | None
    cluster: str  # template_id for template items, item id otherwise
    seen_template: bool | None
    expected_action: Action
    predicted_action: str
    correct: bool
    match_type: Literal["exact", "partial", "none"]
    failure_type: FailureType | None
    latency_ms: int
    input_tokens: int
    output_tokens: int
    cost_usd: float
    pred_sql: str | None
    error: str | None


class RunManifest(BaseModel):
    """5.6 Run manifest."""
    run_id: str
    timestamp: str
    setup: str
    model_id: str
    temperature: float
    max_tokens: int
    harness_flags: dict[str, Any]
    system_prompt: str
    test_file_sha256: str
    git_commit: str
    item_count: int
