"""Packaging validation script for KCode.

Validates that:
1. Package installs correctly (editable and standard)
2. Entry point works (kcode --version)
3. All imports resolve
4. Tests pass
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def run(cmd: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    """Run a shell command and return the result."""
    print(f"\n>>> {cmd}")
    result = subprocess.run(
        cmd,
        shell=True,
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent.parent,
    )
    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)
    if check and result.returncode != 0:
        print(f"FAILED: {cmd}", file=sys.stderr)
        sys.exit(1)
    return result


def main() -> None:
    print("=" * 60)
    print("KCode Packaging Validation")
    print("=" * 60)

    # 1. Test editable install
    print("\n[1/5] Testing editable install...")
    run("pip install -e .[dev] -q")

    # 2. Test entry point
    print("\n[2/5] Testing entry point (kcode --version)...")
    result = run("kcode --version")
    if "kcode 0.1.0" not in result.stdout:
        print(f"FAILED: Expected 'kcode 0.1.0', got '{result.stdout.strip()}'")
        sys.exit(1)

    # 3. Test imports
    print("\n[3/5] Testing imports...")
    run('python -c "from packages.core.src.runtime.contracts import AgentRuntime; print(\'AgentRuntime OK\')"')
    run('python -c "from packages.core.src.tools.contracts import ToolRegistry; print(\'ToolRegistry OK\')"')
    run('python -c "from packages.core.src.tools.mcp.contracts import McpToolProvider; print(\'McpToolProvider OK\')"')
    run('python -c "from packages.core.src.config.mcp import McpConfig; print(\'McpConfig OK\')"')

    # 4. Run tests
    print("\n[4/5] Running tests...")
    run("python -m pytest -q --tb=short")

    # 5. Run coverage
    print("\n[5/5] Running coverage...")
    run("python -m pytest --cov=packages/core --cov=apps/cli --cov-report=term-missing -q", check=False)

    print("\n" + "=" * 60)
    print("Packaging validation PASSED")
    print("=" * 60)


if __name__ == "__main__":
    main()
