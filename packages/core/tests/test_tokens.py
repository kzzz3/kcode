from __future__ import annotations

from packages.core.src.context.tokens import ContextBudget, TokenCounter
from packages.core.src.models.interfaces import Message


def test_token_counter_fallback_counts_text() -> None:
    counter = TokenCounter.__new__(TokenCounter)
    counter._model = "unknown-model"
    counter._encoder = None

    assert counter.count_text("abcd") == 1
    assert counter.uses_tiktoken is False


def test_token_counter_includes_overhead() -> None:
    counter = TokenCounter.__new__(TokenCounter)
    counter._model = "unknown-model"
    counter._encoder = None

    message = Message(role="user", content="hi")
    assert counter.count_message(message) >= 5


def test_token_counter_counts_tool_calls_and_tool_call_id() -> None:
    counter = TokenCounter.__new__(TokenCounter)
    counter._model = "unknown-model"
    counter._encoder = None

    message = Message(
        role="assistant",
        content=None,
        tool_calls=[{"function": {"name": "x", "arguments": {"a": 1}}}],
        tool_call_id="tool-1",
    )
    count = counter.count_message(message)
    assert count > 6


def test_context_budget_reports_utilization() -> None:
    budget = ContextBudget.__new__(ContextBudget)
    budget._model = "unknown-model"
    budget._context_window = 100
    budget._reserve_tokens = 10
    budget._used_tokens = 0

    budget.update(used_tokens=40)

    assert budget.used_tokens == 40
    assert budget.available == 50
    assert budget.remaining == 60
    assert budget.utilization == 0.4


def test_context_budget_clamps_negative_remaining() -> None:
    budget = ContextBudget.__new__(ContextBudget)
    budget._model = "unknown-model"
    budget._context_window = 10
    budget._reserve_tokens = 5
    budget._used_tokens = 0

    budget.update(used_tokens=999)

    assert budget.remaining == 0
    assert budget.available == 0


def test_token_counter_fallback_counts_empty_text_as_one_token() -> None:
    counter = TokenCounter.__new__(TokenCounter)
    counter._model = "unknown-model"
    counter._encoder = None

    assert counter.count_text("") == 1


def test_token_counter_scales_with_length() -> None:
    counter = TokenCounter.__new__(TokenCounter)
    counter._model = "unknown-model"
    counter._encoder = None

    assert counter.count_text("a" * 400) > counter.count_text("abcd")


def test_context_budget_update_zero_tokens_baseline() -> None:
    budget = ContextBudget.__new__(ContextBudget)
    budget._model = "unknown-model"
    budget._context_window = 100
    budget._reserve_tokens = 10
    budget._used_tokens = 10

    budget.update(used_tokens=0)

    assert budget.used_tokens == 0
    assert budget.available == 90
    assert budget.remaining == 100
    assert budget.utilization == 0.0


def test_context_budget_can_fit_exact_boundary() -> None:
    budget = ContextBudget.__new__(ContextBudget)
    budget._model = "unknown-model"
    budget._context_window = 100
    budget._reserve_tokens = 10
    budget._used_tokens = 0

    # Available capacity = 100 - 10 = 90
    assert budget.can_fit(90) is True
    assert budget.can_fit(91) is False


def test_context_budget_can_fit_with_existing_usage() -> None:
    budget = ContextBudget.__new__(ContextBudget)
    budget._model = "unknown-model"
    budget._context_window = 1000
    budget._reserve_tokens = 100
    budget._used_tokens = 500

    # Available = 1000 - 100 - 500 = 400
    assert budget.can_fit(400) is True
    assert budget.can_fit(401) is False
