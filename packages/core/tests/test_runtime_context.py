"""Tests for packages/core/src/runtime/context.py."""
from __future__ import annotations

from pathlib import Path

from packages.core.src.runtime.context import RuntimeContext


def _make_ctx() -> RuntimeContext:
    return RuntimeContext(
        cwd=Path("/tmp/work"),
        workspace_root=Path("/tmp/workspace"),
        config_paths=(Path("/tmp/c1.yaml"), Path("/tmp/c2.yaml")),
        is_interactive=False,
        debug=False,
        extra={"key": "value"},
    )


def test_with_overrides_cwd() -> None:
    ctx = _make_ctx()
    new_ctx = ctx.with_overrides(cwd=Path("/other"))
    assert new_ctx.cwd == Path("/other")
    assert ctx.cwd == Path("/tmp/work")  # original unchanged


def test_with_overrides_multiple_fields() -> None:
    ctx = _make_ctx()
    new_ctx = ctx.with_overrides(is_interactive=True, debug=True)
    assert new_ctx.is_interactive is True
    assert new_ctx.debug is True
    assert new_ctx.workspace_root == ctx.workspace_root


def test_with_overrides_preserves_extra() -> None:
    ctx = _make_ctx()
    new_ctx = ctx.with_overrides(debug=True)
    assert new_ctx.extra == {"key": "value"}


def test_with_overrides_extra_gets_merged_not_replaced() -> None:
    ctx = _make_ctx()
    new_ctx = ctx.with_overrides(extra={"a": 1})
    # extra is replaced entirely (update semantics), original preserved
    assert ctx.extra == {"key": "value"}
    assert new_ctx.extra == {"a": 1}


def test_with_overrides_none_extra() -> None:
    ctx = RuntimeContext(
        cwd=Path("/tmp"),
        workspace_root=Path("/tmp"),
        config_paths=(),
        extra=None,
    )
    new_ctx = ctx.with_overrides(debug=True)
    assert new_ctx.extra == {}


def test_frozen_dataclass() -> None:
    ctx = _make_ctx()
    try:
        ctx.cwd = Path("/nope")  # type: ignore[misc]
        assert False, "Should have raised"
    except AttributeError:
        pass
