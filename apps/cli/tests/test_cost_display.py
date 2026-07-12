"""Tests for cost/token display helpers in chat.py."""
from __future__ import annotations

import importlib

_chat = importlib.import_module("apps.cli.src.commands.chat")


class TestEstimateCost:
  """_estimate_cost returns correct dollar amounts or None for unknown models."""

  def test_known_model(self) -> None:
    cost = _chat._estimate_cost("gpt-4o", 1000, 500)
    expected = (1000 / 1_000_000) * 2.50 + (500 / 1_000_000) * 10.00
    assert cost is not None
    assert abs(cost - expected) < 1e-9

  def test_unknown_model_returns_none(self) -> None:
    assert _chat._estimate_cost("unknown-model-xyz", 1000, 1000) is None

  def test_zero_tokens(self) -> None:
    assert _chat._estimate_cost("gpt-4o", 0, 0) == 0.0

  def test_large_token_count(self) -> None:
    cost = _chat._estimate_cost("gpt-4o", 100_000, 50_000)
    assert cost is not None
    assert 0.0 < cost < 10.0


class TestFormatUsageLine:
  """_format_usage_line produces readable output."""

  def test_basic_output(self) -> None:
    line = _chat._format_usage_line(
      usage={"prompt_tokens": 1500, "completion_tokens": 800},
      model="gpt-4o",
    )
    assert "1,500" in line
    assert "800" in line
    assert "$" in line

  def test_zero_cost_model(self) -> None:
    line = _chat._format_usage_line(
      usage={"prompt_tokens": 100, "completion_tokens": 50},
      model="unknown-model",
    )
    assert "100" in line
    assert "50" in line
    assert "$" not in line