"""Run every cheap quality gate, in order, and report which ones failed.

This is the quality bar made executable. CI runs this same script, so a gate cannot pass
locally and be missing in CI, or the other way round.

Deliberate boundary: only gates that are fast and need no network live here. Anything that
needs a model, a browser, the CMS download or the internet gets its own command, because a
check that takes minutes stops being run before a commit.

Usage:
    uv run python tools/check.py               # run everything, report at the end
    uv run python tools/check.py --fail-fast   # stop at the first failing gate
    uv run python tools/check.py lint types    # run a subset by name
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Gate:
    """One quality gate: a name, the command that enforces it, and why it exists.

    Attributes:
        name: Short selector used on the command line.
        why: The failure this gate is here to prevent, in one line.
        command: Argument vector, run from the repository root.
    """

    name: str
    why: str
    command: tuple[str, ...]


#: The gates, cheapest first, so an obvious failure shows up in seconds.
GATES: tuple[Gate, ...] = (
    Gate(
        name="format",
        why="formatting arguments in review waste the review",
        command=("ruff", "format", "--check", "."),
    ),
    Gate(
        name="lint",
        why="unused names, missing docstrings and unsafe calls compound quietly",
        command=("ruff", "check", "."),
    ),
    Gate(
        name="floor",
        why="a silenced check, a skipped test or a pasted key is the bar lowered unannounced",
        command=(sys.executable, "tools/floor.py"),
    ),
    Gate(
        name="types",
        why="strict types catch the wrong-shape value before a test has to",
        command=("pyright",),
    ),
    Gate(
        name="tests",
        why="coverage below the floor means a change can land with nothing watching it",
        command=("pytest", "--cov", "--cov-report=term-missing:skip-covered"),
    ),
)


def say(message: str) -> None:
    """Print a line and flush it, so it lands before the next gate's own output."""
    print(message, flush=True)


def run_gate(gate: Gate) -> tuple[bool, float]:
    """Run one gate from the repository root, streaming its output.

    Args:
        gate: The gate to run.

    Returns:
        `(passed, seconds)`.
    """
    say(f"\n\033[1m-- {gate.name}\033[0m  ({gate.why})")
    started = time.monotonic()
    try:
        completed = subprocess.run(gate.command, cwd=ROOT, check=False)
    except FileNotFoundError:
        say(f"   command not found: {gate.command[0]} -- run `uv sync --all-groups` first")
        return False, time.monotonic() - started
    return completed.returncode == 0, time.monotonic() - started


def select(names: Sequence[str]) -> list[Gate]:
    """Pick the gates named on the command line, keeping the declared order.

    Args:
        names: Gate names, or empty for all of them.

    Raises:
        SystemExit: If a name matches no gate.
    """
    if not names:
        return list(GATES)
    known = {gate.name for gate in GATES}
    unknown = sorted(set(names) - known)
    if unknown:
        raise SystemExit(
            f"unknown gate(s): {', '.join(unknown)}. known: {', '.join(sorted(known))}"
        )
    return [gate for gate in GATES if gate.name in set(names)]


def main(argv: Sequence[str] | None = None) -> int:
    """Run the selected gates and return a process exit code: 0 if all passed, else 1."""
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("gates", nargs="*", help="gate names to run (default: all)")
    parser.add_argument("--fail-fast", action="store_true", help="stop at the first failure")
    args = parser.parse_args(argv)

    results: list[tuple[Gate, bool, float]] = []
    for gate in select(args.gates):
        passed, elapsed = run_gate(gate)
        results.append((gate, passed, elapsed))
        if not passed and args.fail_fast:
            break

    say("\n\033[1m-- summary\033[0m")
    for gate, passed, elapsed in results:
        mark = "\033[32mpass\033[0m" if passed else "\033[31mFAIL\033[0m"
        say(f"   {mark}  {gate.name:<7} {elapsed:5.1f}s")

    failed = [gate.name for gate, passed, _ in results if not passed]
    total = sum(elapsed for _, _, elapsed in results)
    if failed:
        say(f"\n{len(failed)} gate(s) failed: {', '.join(failed)}  ({total:.1f}s)")
        return 1
    say(f"\nall {len(results)} gate(s) passed  ({total:.1f}s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
