"""The `policylens` command line.

Commands:
    ingest-ncd PACKAGE [--out PATH] [--allow-dropped-rows]
        Build the database from a downloaded `ncd.zip` and print what was stored, withheld,
        dropped and flagged.

Exit codes: 0 when the database was built; 1 when rows were dropped and that wasn't
explicitly allowed (the database is not replaced); 2 when the package or the build failed a
check. Dropped rows fail by default because the weekly build runs unattended, and a quietly
shrinking corpus is the failure nobody notices.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from policylens.ingest.ncd import NCD_TABLES, Issue, Severity, parse_ncd
from policylens.ingest.package import PackageError, read_package
from policylens.store.build import BuildError, build_database

#: Where the database goes unless told otherwise. Ignored by git: it is built, not committed.
DEFAULT_DATABASE = Path("data/build/policylens.sqlite")

#: How many individual issues to print before summarising the rest.
SHOWN_ISSUES = 20


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command line and return the process exit code."""
    parser = argparse.ArgumentParser(
        prog="policylens", description="Build and query the policylens coverage database."
    )
    commands = parser.add_subparsers(dest="command", required=True)
    ingest = commands.add_parser("ingest-ncd", help="build the database from an NCD package")
    ingest.add_argument("package", type=Path, help="the downloaded ncd.zip")
    ingest.add_argument("--out", type=Path, default=DEFAULT_DATABASE, help="database to write")
    ingest.add_argument(
        "--allow-dropped-rows",
        action="store_true",
        help="build even if some rows broke the data dictionary and were dropped",
    )
    args = parser.parse_args(argv)
    return _ingest_ncd(args.package, args.out, allow_dropped=args.allow_dropped_rows)


def _ingest_ncd(package_path: Path, out: Path, *, allow_dropped: bool) -> int:
    """Read, parse, report, and build unless dropped rows forbid it."""
    try:
        package = read_package(package_path, NCD_TABLES)
    except (PackageError, OSError) as error:
        _say(f"cannot read {package_path}: {error}")
        return 2

    data = parse_ncd(package)
    _say(f"package  {package_path.name}  sha256 {package.sha256}")
    _report(data.issues)
    dropped = sum(1 for issue in data.issues if issue.severity is Severity.ERROR)
    if dropped and not allow_dropped:
        _say(f"\n{dropped} row(s) dropped; database not built. Rerun with --allow-dropped-rows")
        _say("only after reading the issues above.")
        return 1

    try:
        summary = build_database(package, data, out, now=datetime.now(UTC))
    except BuildError as error:
        _say(f"\nbuild refused: {error}")
        return 2
    _say(
        f"\nbuilt {summary.path}: {summary.stored} NCD version(s) stored, "
        f"{summary.withheld} withheld, {summary.errors} row(s) dropped, "
        f"{summary.warnings} warning(s)"
    )
    return 0


def _report(issues: Sequence[Issue]) -> None:
    """Print issues, most serious first, capped so a bad package can't flood the terminal."""
    ordered = sorted(issues, key=lambda issue: issue.severity is not Severity.ERROR)
    for issue in ordered[:SHOWN_ISSUES]:
        where = f"{issue.table} row {issue.row}" + (f" {issue.column}" if issue.column else "")
        _say(f"  {issue.severity.value:<7} {where}: {issue.message}")
    if len(ordered) > SHOWN_ISSUES:
        _say(f"  ... and {len(ordered) - SHOWN_ISSUES} more")


def _say(message: str) -> None:
    """Write one line to standard output."""
    sys.stdout.write(message + "\n")


if __name__ == "__main__":
    sys.exit(main())
