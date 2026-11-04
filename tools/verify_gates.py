"""Prove every gate is connected by making each one fail on purpose.

A gate that has never failed is not known to work. A wrong path, a tool that exits zero
when it finds nothing, an include list that matches no files: each gives a green check that
means nothing. This injects one fault per gate, runs only that gate, and requires it to fail.
Then it removes the faults and requires the full check to be green again.

Deliberate boundary: each fault is the smallest thing that should trip its gate. This shows
a gate fires, not that it catches every class of fault.

Usage:
    uv run python tools/verify_gates.py
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Probe:
    """One deliberate fault, aimed at exactly one gate.

    Attributes:
        gate: The gate name, as `tools/check.py` selects it.
        path: File to create, relative to the repository root.
        content: The faulty contents.
        fault: What is wrong with it, for the report.
    """

    gate: str
    path: Path
    content: str
    fault: str


_PACKAGE_PROBE = Path("src/policylens/_probe.py")

PROBES: tuple[Probe, ...] = (
    Probe("format", _PACKAGE_PROBE, '"""Probe."""\n\nx   =    1\n', "spacing ruff would rewrite"),
    Probe("lint", _PACKAGE_PROBE, '"""Probe."""\n\nimport os\n', "an import nothing uses"),
    Probe(
        "floor",
        _PACKAGE_PROBE,
        # Assembled from pieces so this file doesn't trip the scan itself.
        '"""Probe."""\n\nCOUNT = 1  # ' + "no" + "qa\n",
        "a suppression comment",
    ),
    Probe("types", _PACKAGE_PROBE, '"""Probe."""\n\nCOUNT: int = "one"\n', "a str annotated int"),
    Probe(
        "tests",
        Path("tests/test_probe.py"),
        '"""Probe."""\n\n\ndef test_probe() -> None:\n    assert 1 == 2\n',
        "an assertion that cannot hold",
    ),
    Probe(
        "tests",
        _PACKAGE_PROBE,
        # Far more statements than the tests cover, so the total drops below the floor.
        '"""Probe."""\n\n\ndef never_called() -> int:\n' + "    x = 1\n" * 2000 + "    return x\n",
        "a module nothing tests, below the coverage floor",
    ),
)


def say(message: str) -> None:
    """Print a line and flush it."""
    print(message, flush=True)


def _check(*gates: str) -> int:
    """Run `tools/check.py` for the named gates (all if none) and return its exit code.

    Output is discarded: the gates are expected to fail here, and only the exit code matters.
    """
    command = (sys.executable, "tools/check.py", *gates)
    return subprocess.run(command, cwd=ROOT, capture_output=True, check=False).returncode


def probe(case: Probe) -> bool:
    """Inject one fault, run its gate, and report whether the gate caught it.

    The file is removed again even if the gate misbehaves, so a failed run never leaves a
    broken tree behind.

    Raises:
        SystemExit: If the probe path already exists, which would mean overwriting real work.
    """
    target = ROOT / case.path
    if target.exists():
        raise SystemExit(f"refusing to overwrite an existing file: {case.path.as_posix()}")
    try:
        target.write_text(case.content, encoding="utf-8", newline="\n")
        caught = _check(case.gate) != 0
    finally:
        target.unlink(missing_ok=True)
    mark = "\033[32mcaught\033[0m" if caught else "\033[31mMISSED\033[0m"
    say(f"   {mark}  {case.gate:<7} {case.fault}")
    return caught


def main() -> int:
    """Run every probe, then confirm the tree is green again. Returns 0 only if both hold."""
    say("\033[1m-- injecting one fault per gate\033[0m")
    caught = [probe(case) for case in PROBES]

    say("\n\033[1m-- confirming the tree is green again\033[0m")
    green = _check() == 0
    say(f"   {'green' if green else 'NOT GREEN'}  full check")

    missed = [case.gate for case, ok in zip(PROBES, caught, strict=True) if not ok]
    if missed:
        say(f"\n{len(missed)} gate(s) did not fire: {', '.join(missed)}")
        return 1
    if not green:
        say("\nevery gate fired, but the tree did not return to green")
        return 1
    say(f"\nall {len(PROBES)} faults caught; every gate is connected")
    return 0


if __name__ == "__main__":
    sys.exit(main())
