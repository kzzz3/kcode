"""Extended tests for packages/core/src/context/tokens.py.

Covers: _resolve_encoding_name, _get_tiktoken_encoder, TokenCounter constructor,
count_messages, ContextBudget.__init__ with _infer_context_window, is_overflow, can_fit.
"""
from __future__ import annotations

import sys
import types

from packages.core.src.context.tokens import (
    ContextBudget,
    TokenCounter,
    _get_tiktoken_encoder,
    _resolve_encoding_name,
)
from packages.core.src.models.interfaces import Message


# ---------------------------------------------------------------------------
# _resolve_encoding_name
# ---------------------------------------------------------------------------

def test_resolve_encoding_known_models() -> None:
    assert _resolve_encoding_name("gpt-4o") == "o200k_base"
    assert _resolve_encoding_name("gpt-4-turbo") == "cl100k_base"
    assert _resolve_encoding_name("gpt-4") == "cl100k_base"
    assert _resolve_encoding_name("gpt-3.5-turbo-16k") == "cl100k_base"
    assert _resolve_encoding_name("o1-preview") == "o200k_base"
    assert _resolve_encoding_name("o3-mini") == "o200k_base"
    assert _resolve_encoding_name("deepseek-coder") == "cl100k_base"
    assert _resolve_encoding_name("claude-3-opus") == "cl100k_base"


def test_resolve_encoding_case_insensitive() -> None:
    assert _resolve_encoding_name("GPT-4O") == "o200k_base"
    assert _resolve_encoding_name("Claude-3-Sonnet") == "cl100k_base"


def test_resolve_encoding_unknown_returns_none() -> None:
    assert _resolve_encoding_name("llama-3-8b") is None
    assert _resolve_encoding_name("") is None


# ---------------------------------------------------------------------------
# _get_tiktoken_encoder
# ---------------------------------------------------------------------------

def test_get_tiktoken_encoder_returns_encoder_for_known_model() -> None:
    encoder = _get_tiktoken_encoder("gpt-4o")
    assert encoder is not None
    # Should be able to encode text
    tokens = encoder.encode("hello world")
    assert isinstance(tokens, list)
    assert len(tokens) > 0


def test_get_tiktoken_encoder_returns_none_for_unknown_model() -> None:
    assert _get_tiktoken_encoder("llama-3") is None


def test_get_tiktoken_encoder_returns_none_when_tiktoken_import_fails(monkeypatch) -> None:
    """If tiktoken is unavailable, _get_tiktoken_encoder returns None gracefully."""
    # Force the function to attempt importing tiktoken by clearing any cached module,
    # then point sys.modules to a placeholder whose get_encoding raises.
    monkeypatch.delitem(sys.modules, "tiktoken", raising=False)
    monkeypatch.setitem(sys.modules, "tiktoken", types.ModuleType("tiktoken"))
    broken = sys.modules["tiktoken"]

    def _bad_get_encoding(_name: str) -> None:
        raise RuntimeError("mocked tiktoken failure")

    broken.get_encoding = _bad_get_encoding  # type: ignore[attr-defined]
    result = _get_tiktoken_encoder("gpt-4o")
    assert result is None


# ---------------------------------------------------------------------------
# TokenCounter constructor + uses_tiktoken
# ---------------------------------------------------------------------------

def test_token_counter_known_model_uses_tiktoken() -> None:
    counter = TokenCounter(model="gpt-4o")
    assert counter.uses_tiktoken is True


def test_token_counter_unknown_model_uses_fallback() -> None:
    counter = TokenCounter(model="some-random-model-xyz")
    assert counter.uses_tiktoken is False


def test_token_counter_default_model_is_gpt4o() -> None:
    counter = TokenCounter()
    assert counter.uses_tiktoken is True


# ---------------------------------------------------------------------------
# TokenCounter.count_messages
# ---------------------------------------------------------------------------

def test_count_messages_single_user_message() -> None:
    counter = TokenCounter(model="gpt-4o")
    msgs = [Message(role="user", content="Hello, world!")]
    count = counter.count_messages(msgs)
    # Should be at least content tokens + overhead (4 per msg + 2 request overhead)
    assert count > 4


def test_count_messages_multiple_messages() -> None:
    counter = TokenCounter(model="gpt-4o")
    msgs = [
        Message(role="system", content="You are a helpful assistant."),
        Message(role="user", content="Hi"),
        Message(role="assistant", content="Hello!"),
    ]
    count = counter.count_messages(msgs)
    assert count > 10


def test_count_messages_with_tool_calls() -> None:
    counter = TokenCounter(model="gpt-4o")
    msgs = [
        Message(
            role="assistant",
            content=None,
            tool_calls=[{"function": {"name": "search", "arguments": {"q": "test"}}}],
        ),
    ]
    count = counter.count_messages(msgs)
    assert count > 5


def test_count_messages_empty_list() -> None:
    counter = TokenCounter()
    assert counter.count_messages([]) == 2  # request overhead only


# ---------------------------------------------------------------------------
# ContextBudget.__init__ with _infer_context_window
# ---------------------------------------------------------------------------

def test_context_budget_infers_gpt4o_window() -> None:
    budget = ContextBudget(model="gpt-4o")
    assert budget.context_window == 128_000


def test_context_budget_infers_o1_window() -> None:
    budget = ContextBudget(model="o1-preview")
    assert budget.context_window == 200_000


def test_context_budget_infers_deepseek_window() -> None:
    budget = ContextBudget(model="deepseek-coder-33b")
    assert budget.context_window == 65_536


def test_context_budget_infers_unknown_as_8192() -> None:
    budget = ContextBudget(model="llama-3-8b")
    assert budget.context_window == 8_192


def test_context_budget_explicit_window_overrides_inference() -> None:
    budget = ContextBudget(model="gpt-4o", context_window=50_000)
    assert budget.context_window == 50_000


def test_context_budget_custom_reserve() -> None:
    budget = ContextBudget(model="gpt-4o", reserve_tokens=8192)
    assert budget._reserve_tokens == 8192


# ---------------------------------------------------------------------------
# ContextBudget.is_overflow
# ---------------------------------------------------------------------------

def test_context_budget_is_overflow_true_when_over() -> None:
    budget = ContextBudget(model="gpt-4o", context_window=100, reserve_tokens=10)
    budget.update(95)
    assert budget.is_overflow is True


def test_context_budget_is_overflow_false_when_under() -> None:
    budget = ContextBudget(model="gpt-4o", context_window=100, reserve_tokens=10)
    budget.update(80)
    assert budget.is_overflow is False


def test_context_budget_is_overflow_exact_boundary() -> None:
    budget = ContextBudget(model="gpt-4o", context_window=100, reserve_tokens=10)
    budget.update(90)  # exactly context_window - reserve
    assert budget.is_overflow is False


def test_context_budget_utilization_zero_context_window() -> None:
    budget = ContextBudget(model="gpt-4o", context_window=0)
    assert budget.utilization == 1.0
