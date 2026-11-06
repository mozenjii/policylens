"""Build the database file from a parsed package, and open it read-only.

The build writes to a temporary file beside the target and renames it into place only after
every check passes: the licence gate, SQLite's integrity check and its foreign-key check. A
failed build leaves the previous database untouched, so a bad CMS snapshot can never replace
a good one.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from policylens import licence
from policylens.ingest.ncd import Issue, NcdData, NcdVersion, Severity
from policylens.ingest.package import Package
from policylens.store.schema import SCHEMA, SCHEMA_VERSION


class BuildError(Exception):
    """The database failed a check and was not put in place."""


class SchemaVersionError(Exception):
    """The database was built for a schema this code doesn't understand."""


@dataclass(frozen=True, slots=True)
class BuildSummary:
    """What a build produced, for the ingest report.

    Attributes:
        path: The database file.
        package_sha256: The snapshot it was built from.
        stored: NCD versions stored.
        withheld: NCD versions kept out under the licence rule.
        errors: Rows the parser dropped.
        warnings: Rows kept with something the data dictionary doesn't define.
    """

    path: Path
    package_sha256: str
    stored: int
    withheld: int
    errors: int
    warnings: int


def build_database(package: Package, data: NcdData, target: Path, *, now: datetime) -> BuildSummary:
    """Write a new database for one NCD package and move it into place.

    Args:
        package: The package the data came from, for provenance.
        data: The parsed NCD tables.
        target: Where the database should end up. An existing file is replaced only on success.
        now: The build time to record. Passed in so a build is reproducible in tests.

    Returns:
        A summary of what was stored.

    Raises:
        BuildError: If the licence gate, the integrity check or the foreign-key check fails.
    """
    temporary = target.with_name(target.name + ".building")
    temporary.unlink(missing_ok=True)
    target.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(temporary)
    try:
        connection.executescript(SCHEMA)
        stored, withheld = _write(connection, package, data, now)
        verify_database(connection)
        connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        connection.commit()
    except BaseException:
        connection.close()
        temporary.unlink(missing_ok=True)
        raise
    connection.close()
    # An atomic rename on the same filesystem: readers see the old file or the new, never half.
    temporary.replace(target)

    return BuildSummary(
        path=target,
        package_sha256=package.sha256,
        stored=stored,
        withheld=len(withheld),
        errors=sum(1 for issue in data.issues if issue.severity is Severity.ERROR),
        warnings=sum(1 for issue in data.issues if issue.severity is Severity.WARNING),
    )


def open_readonly(path: Path) -> sqlite3.Connection:
    """Open a built database so that nothing can write to it.

    Raises:
        FileNotFoundError: If there is no database at `path`.
        SchemaVersionError: If it was built for a different schema version.
    """
    if not path.is_file():
        raise FileNotFoundError(path)
    connection = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
    connection.execute("PRAGMA query_only = ON")
    (version,) = connection.execute("PRAGMA user_version").fetchone()
    if version != SCHEMA_VERSION:
        connection.close()
        raise SchemaVersionError(
            f"{path.name} has schema {version}, this code reads {SCHEMA_VERSION}"
        )
    return connection


def _write(
    connection: sqlite3.Connection, package: Package, data: NcdData, now: datetime
) -> tuple[int, list[NcdVersion]]:
    """Insert everything; return how many versions were stored and which were withheld."""
    connection.execute(
        "INSERT INTO snapshot VALUES (?, ?, ?, ?)",
        (package.sha256, "ncd", package.path.name, now.isoformat()),
    )
    connection.executemany(
        "INSERT INTO publication VALUES (?, ?, ?)",
        [(code, number, title) for code, (number, title) in data.publications.items()],
    )
    connection.executemany(
        "INSERT INTO benefit_category VALUES (?, ?)", list(data.benefit_categories.items())
    )

    withheld = [v for v in data.versions.values() if licence.withhold_reason(v) is not None]
    withheld_keys = {(v.ncd_id, v.version) for v in withheld}
    stored = [v for v in data.versions.values() if (v.ncd_id, v.version) not in withheld_keys]
    connection.executemany(_INSERT_NCD_VERSION, [_version_row(v) for v in stored])
    connection.executemany(
        "INSERT INTO ncd_benefit_category VALUES (?, ?, ?)",
        [link for link in data.version_benefits if link[:2] not in withheld_keys],
    )
    connection.executemany(
        "INSERT INTO ingest_issue VALUES ('ncd', ?, ?, ?, ?, ?)",
        [*_issue_rows(data.issues), *_withheld_rows(withheld)],
    )
    return len(stored), withheld


def verify_database(connection: sqlite3.Connection) -> None:
    """Run every check that must pass before a database may be used.

    The build runs it before moving a new file into place. It is public so a database can be
    re-checked later, for example just before a deploy.

    Raises:
        BuildError: Naming the first check that failed.
    """
    violations = licence.check_schema(connection)
    if violations:
        raise BuildError("licence gate: " + "; ".join(violations))
    (integrity,) = connection.execute("PRAGMA integrity_check").fetchone()
    if integrity != "ok":
        raise BuildError(f"integrity check: {integrity}")
    orphans = connection.execute("PRAGMA foreign_key_check").fetchall()
    if orphans:
        raise BuildError(f"foreign key check: {len(orphans)} row(s) point at nothing")


#: Columns are named so the insert can't silently shift if the table's column order changes.
_INSERT_NCD_VERSION = """
INSERT INTO ncd_version (
    ncd_id, version, is_ncd, coverage_level, coverage_level_code, manual_section,
    manual_section_title, effective_date, implementation_date, termination_date,
    item_service_description, indications_limitations, cross_reference, other_text,
    transmittal_number, transmittal_issued, transmittal_url, change_request_number,
    publication_code, revision_history, under_review, created_at, last_updated_at,
    last_cleared_at, is_lab, keywords
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""


def _version_row(version: NcdVersion) -> tuple[object, ...]:
    """One `ncd_version` row, in `_INSERT_NCD_VERSION`'s column order."""
    return (
        version.ncd_id,
        version.version,
        int(version.is_ncd),
        version.coverage_level.value,
        version.coverage_level_code,
        version.manual_section,
        version.manual_section_title,
        version.effective_date.isoformat(),
        _iso(version.implementation_date),
        _iso(version.termination_date),
        version.item_service_description,
        version.indications_limitations,
        version.cross_reference,
        version.other_text,
        version.transmittal_number,
        _iso(version.transmittal_issued),
        version.transmittal_url,
        version.change_request_number,
        version.publication_code,
        version.revision_history,
        int(version.under_review),
        version.created_at.isoformat(),
        version.last_updated_at.isoformat(),
        version.last_cleared_at.isoformat(),
        int(version.is_lab),
        version.keywords,
    )


def _issue_rows(issues: Iterable[Issue]) -> list[tuple[object, ...]]:
    """Parser issues as `ingest_issue` rows (without the dataset column)."""
    return [(i.table, i.row, i.column, i.severity.value, i.message) for i in issues]


def _withheld_rows(withheld: Iterable[NcdVersion]) -> list[tuple[object, ...]]:
    """One warning per withheld version, so the report says what was left out and why."""
    rows: list[tuple[object, ...]] = []
    for version in withheld:
        reason = licence.withhold_reason(version)
        message = f"NCD {version.ncd_id} version {version.version} {reason}"
        rows.append(("ncd_trkg", None, "ncd_ama", Severity.WARNING.value, message))
    return rows


def _iso(value: date | None) -> str | None:
    """A date as ISO text, keeping None."""
    return None if value is None else value.isoformat()
