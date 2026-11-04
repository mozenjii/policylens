"""Refuse the ways a quality bar gets lowered without anyone deciding to lower it.

Linters and type checkers can be silenced line by line, tests can be skipped, an
unfinished function can pretend to be finished, and a key can be pasted into a file. None
of those fails a normal check; each is the check being switched off. This scan fails on
all of them.

Rules:
    suppression   `noqa`, `type: ignore`, `pyright: ignore` or `pragma: no cover` in Python.
    skip          A pytest skip or skipif with no `reason=`. A skip that can't say why is
                  a deleted test.
    stub          `raise NotImplementedError` in the package. Unbuilt behaviour is
                  disabled explicitly, never shipped as a function that throws later.
    swallow       An `except` whose whole body is `pass`. A failure that disappears is
                  worse than one that crashes.
    secret        Something shaped like a cloud, GitHub or model-provider API credential,
                  or a private key, in any text file.

Deliberate boundary: this is a pattern scan, not a proof. It catches the common forms
cheaply on every commit; review catches the rest.

Usage:
    uv run python tools/floor.py            # scan every file git would commit
    uv run python tools/floor.py a.py b.py  # scan just these
"""

from __future__ import annotations

import re
import subprocess
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

#: Binary and generated files: scanning them finds nothing and costs time.
SKIPPED_SUFFIXES = frozenset({".png", ".jpg", ".jpeg", ".gif", ".pdf", ".zip", ".ico", ".lock"})


@dataclass(frozen=True)
class Finding:
    """One rule broken at one place.

    Attributes:
        path: File, relative to the repository root, with forward slashes.
        line: 1-based line number.
        rule: Rule name from the module docstring.
        text: The offending line, stripped, so the report can be read without opening the file.
    """

    path: str
    line: int
    rule: str
    text: str


_SUPPRESSION = re.compile(r"#\s*(noqa\b|type:\s*ignore|pyright:\s*ignore|pragma:\s*no\s*cover)")
_SKIP = re.compile(r"pytest\.(mark\.skip(if)?\b|skip\()")
_STUB = re.compile(r"\braise\s+NotImplementedError\b")
_EXCEPT = re.compile(r"^(\s*)except\b.*:\s*(#.*)?$")
_PASS = re.compile(r"^\s*pass\s*(#.*)?$")
_SECRETS = (
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"\b(ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{30,}"),
    # Assembled, so the prefix never appears whole in the repository for another scanner to flag.
    re.compile("github" + r"_pat_[A-Za-z0-9_]{30,}"),
    re.compile(r"\bsk-(ant-|proj-)?[A-Za-z0-9_-]{20,}"),
    re.compile(r"-----BEGIN (RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
)


def scan_text(path: str, text: str) -> list[Finding]:
    """Scan one file's contents.

    Args:
        path: The file's repository-relative path. It decides which rules apply: the Python
            rules only to `.py` files, and the stub rule only inside `src/`.
        text: The file's contents.

    Returns:
        Every finding, in line order.
    """
    lines = text.splitlines()
    findings: list[Finding] = []

    def add(index: int, rule: str) -> None:
        findings.append(Finding(path, index + 1, rule, lines[index].strip()))

    is_python = path.endswith(".py")
    in_package = path.startswith("src/")
    for index, line in enumerate(lines):
        if any(pattern.search(line) for pattern in _SECRETS):
            add(index, "secret")
        if not is_python:
            continue
        if _SUPPRESSION.search(line):
            add(index, "suppression")
        if _SKIP.search(line) and "reason=" not in line:
            add(index, "skip")
        if in_package and _STUB.search(line):
            add(index, "stub")
        if _swallows(lines, index):
            add(index, "swallow")
    return findings


def _swallows(lines: Sequence[str], index: int) -> bool:
    """Whether the `except` on this line has a body of nothing but `pass`.

    Comment and blank lines inside the block are skipped; the block ends at the first line
    indented no deeper than the `except` itself.
    """
    header = _EXCEPT.match(lines[index])
    if header is None:
        return False
    depth = len(header.group(1))
    body: list[str] = []
    for line in lines[index + 1 :]:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if len(line) - len(line.lstrip()) <= depth:
            break
        body.append(line)
    return len(body) == 1 and _PASS.match(body[0]) is not None


def scan_files(paths: Iterable[str], root: Path = ROOT) -> list[Finding]:
    """Scan files by repository-relative path, skipping binaries and unreadable files.

    Args:
        paths: Paths relative to `root`.
        root: The directory the paths are relative to.

    Returns:
        Every finding across all files.
    """
    findings: list[Finding] = []
    for relative in paths:
        if Path(relative).suffix.lower() in SKIPPED_SUFFIXES:
            continue
        try:
            text = (root / relative).read_text(encoding="utf-8")
        except (UnicodeDecodeError, FileNotFoundError):
            # Not text, or listed by git but deleted in the working tree: nothing to scan.
            continue
        findings.extend(scan_text(relative.replace("\\", "/"), text))
    return findings


def committable_files(root: Path = ROOT) -> list[str]:
    """List the files git would commit: tracked, plus untracked ones that aren't ignored."""
    completed = subprocess.run(
        ("git", "ls-files", "--cached", "--others", "--exclude-standard"),
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    )
    return [line for line in completed.stdout.splitlines() if line]


def main(argv: Sequence[str] | None = None, root: Path = ROOT) -> int:
    """Scan and print findings. Returns 0 when there are none, 1 otherwise.

    Args:
        argv: Paths relative to `root`, or empty to scan every committable file.
        root: The repository root.
    """
    paths = list(argv) if argv else committable_files(root)
    findings = scan_files(paths, root)
    for finding in findings:
        print(f"{finding.path}:{finding.line}: {finding.rule}: {finding.text}")
    if findings:
        print(f"\n{len(findings)} finding(s). Fix the cause; don't silence the check.")
        return 1
    print(f"floor: {len(paths)} file(s) clean")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
