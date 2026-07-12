"""Token counting and context budget management.

Provides accurate token counting via tiktoken for OpenAI-family models,
with a char-based fallback for unknown model families.
"""
from __future__ import annotations

import logging
from typing import Any

from packages.core.src.models.interfaces import Message

_LOGGER = logging.getLogger(__name__)

# Model family -> tiktoken encoding name
_MODEL_ENCODING_MAP: dict[str, str] = {
  "gpt-4o": "o200k_base",
  "gpt-4-turbo": "cl100k_base",
  "gpt-4": "cl100k_base",
  "gpt-3.5-turbo": "cl100k_base",
  "o1": "o200k_base",
  "o3": "o200k_base",
  "o4": "o200k_base",
  "deepseek": "cl100k_base",
  "claude": "cl100k_base",
}

# Default context window sizes (tokens) for well-known models
_DEFAULT_CONTEXT_WINDOWS: dict[str, int] = {
  "gpt-4o": 128_000,
  "gpt-4-turbo": 128_000,
  "gpt-4": 8_192,
  "gpt-3.5-turbo": 16_385,
  "o1": 200_000,
  "o3": 200_000,
  "o4": 200_000,
  "deepseek-chat": 65_536,
  "deepseek-coder": 65_536,
  "claude-3-opus": 200_000,
  "claude-3-sonnet": 200_000,
  "claude-3-haiku": 200_000,
}

# Overhead tokens per message (role, separators, etc.) — OpenAI format
_MESSAGE_OVERHEAD_TOKENS = 4
# Per-request overhead (reply priming)
_REQUEST_OVERHEAD_TOKENS = 2


def _resolve_encoding_name(model: str) -> str | None:
  """Map a model name to its tiktoken encoding, or None if unknown."""
  model_lower = model.lower()
  for prefix, encoding in _MODEL_ENCODING_MAP.items():
    if prefix in model_lower:
      return encoding
  return None


def _get_tiktoken_encoder(model: str) -> Any | None:
  """Get a tiktoken encoder for the given model, or None on failure."""
  encoding_name = _resolve_encoding_name(model)
  if encoding_name is None:
    return None
  try:
    import tiktoken
    return tiktoken.get_encoding(encoding_name)
  except Exception:  # noqa: BLE001
    _LOGGER.debug("Failed to load tiktoken encoding %s", encoding_name)
    return None


class TokenCounter:
  """Counts tokens for messages using tiktoken or char-based estimation.

  Usage:
    counter = TokenCounter(model="gpt-4o")
    count = counter.count_messages(messages)
  """

  def __init__(self, model: str = "gpt-4o") -> None:
    self._model = model
    self._encoder = _get_tiktoken_encoder(model)

  @property
  def uses_tiktoken(self) -> bool:
    """True if using tiktoken (accurate), False if char-based fallback."""
    return self._encoder is not None

  def count_text(self, text: str) -> int:
    """Count tokens in a plain text string."""
    if self._encoder is not None:
      return len(self._encoder.encode(text))
    # Fallback: ~4 chars per token (conservative for English)
    return max(1, len(text) // 4)

  def count_message(self, message: Message) -> int:
    """Count tokens in a single Message."""
    total = _MESSAGE_OVERHEAD_TOKENS
    if message.content:
      total += self.count_text(message.content)
    if message.tool_calls:
      import json
      for tc in message.tool_calls:
        fn = tc.get("function", {})
        total += self.count_text(fn.get("name", ""))
        args = fn.get("arguments", {})
        args_str = json.dumps(args) if isinstance(args, dict) else str(args)
        total += self.count_text(args_str)
        total += 4  # tool call framing overhead
    if message.tool_call_id:
      total += self.count_text(message.tool_call_id)
    return total

  def count_messages(self, messages: list[Message]) -> int:
    """Count total tokens across a list of messages."""
    total = _REQUEST_OVERHEAD_TOKENS
    for msg in messages:
      total += self.count_message(msg)
    return total


class ContextBudget:
  """Tracks token usage against a model's context window limit.

  Usage:
    budget = ContextBudget(model="gpt-4o")
    budget.update(used_tokens=1000)
    print(budget.remaining, budget.utilization)
  """

  def __init__(
    self,
    model: str = "gpt-4o",
    context_window: int | None = None,
    reserve_tokens: int = 4096,
  ) -> None:
    self._model = model
    self._context_window = self._infer_context_window(model) if context_window is None else context_window
    self._reserve_tokens = reserve_tokens  # Reserved for response
    self._used_tokens = 0

  @staticmethod
  def _infer_context_window(model: str) -> int:
    """Infer context window size from model name."""
    model_lower = model.lower()
    for prefix, size in _DEFAULT_CONTEXT_WINDOWS.items():
      if prefix in model_lower:
        return size
    # Conservative default for unknown models
    return 8_192

  @property
  def context_window(self) -> int:
    return self._context_window

  @property
  def used_tokens(self) -> int:
    return self._used_tokens

  @property
  def available(self) -> int:
    """Tokens available for prompt content (total minus response reserve)."""
    return max(0, self._context_window - self._reserve_tokens - self._used_tokens)

  @property
  def remaining(self) -> int:
    """Tokens remaining including response reserve."""
    return max(0, self._context_window - self._used_tokens)

  @property
  def utilization(self) -> float:
    """Fraction of context window used (0.0 to 1.0)."""
    if self._context_window <= 0:
      return 1.0
    return self._used_tokens / self._context_window

  @property
  def is_overflow(self) -> bool:
    """True if used tokens exceed available budget."""
    return self._used_tokens > (self._context_window - self._reserve_tokens)

  def update(self, used_tokens: int) -> None:
    """Update the current token usage count."""
    self._used_tokens = used_tokens

  def can_fit(self, additional_tokens: int) -> bool:
    """Check if additional tokens fit within the budget."""
    return (self._used_tokens + additional_tokens) <= (self._context_window - self._reserve_tokens)
