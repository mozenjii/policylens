"""What the database may contain under the licence terms of the CMS download.

The Medicare Coverage Database download comes with AMA (CPT), ADA (CDT) and AHA (UB-04)
licence terms. The CPT terms forbid passing copies to anyone not bound by them, and this
service is public. So the rule is: **nothing licensed is stored**, and that is checked
mechanically rather than remembered.

Two checks enforce it:

- `check_schema` reads the built database's own schema and requires every table and column
  to appear in `REVIEWED`, classified by a person. A column nobody has classified fails the
  build, as does any column classified `LICENSED`. That catches the easy mistake: someone
  maps a new CMS column straight into the store without thinking about what it holds.
- `withhold_reason` keeps out whole documents that CMS itself flags as carrying CPT content.

Deliberate boundary: this decides what may be stored. It doesn't scan free text for code
descriptions; that needs the code lists and arrives with the LCD and Article data, which is
where the descriptor columns live.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from enum import StrEnum

from policylens.ingest.ncd import NcdVersion


class Classification(StrEnum):
    """What a stored column holds, for licence purposes."""

    CMS_TEXT = "cms_text"
    """Prose written by CMS or its contractors."""
    REFERENCE = "reference"
    """Identifiers, dates, flags, URLs and code numbers: facts, not licensed descriptions."""
    PROVENANCE = "provenance"
    """Our own bookkeeping about where the data came from and what ingest found."""
    LICENSED = "licensed"
    """Third-party licensed text, such as a CPT, CDT or UB-04 description. Never stored."""


_C = Classification

#: Every stored table and column, classified. Adding a column to the store means adding it
#: here, which is the point: it forces the question "may we serve this?" to be answered.
REVIEWED: Mapping[str, Mapping[str, Classification]] = {
    "snapshot": {
        "package_sha256": _C.PROVENANCE,
        "dataset": _C.PROVENANCE,
        "package_name": _C.PROVENANCE,
        "built_at": _C.PROVENANCE,
    },
    "ingest_issue": {
        "dataset": _C.PROVENANCE,
        "table_name": _C.PROVENANCE,
        "row_number": _C.PROVENANCE,
        "column_name": _C.PROVENANCE,
        "severity": _C.PROVENANCE,
        "message": _C.PROVENANCE,
    },
    "ncd_version": {
        "ncd_id": _C.REFERENCE,
        "version": _C.REFERENCE,
        "is_ncd": _C.REFERENCE,
        "coverage_level": _C.REFERENCE,
        "coverage_level_code": _C.REFERENCE,
        "manual_section": _C.REFERENCE,
        "manual_section_title": _C.CMS_TEXT,
        "effective_date": _C.REFERENCE,
        "implementation_date": _C.REFERENCE,
        "termination_date": _C.REFERENCE,
        "item_service_description": _C.CMS_TEXT,
        "indications_limitations": _C.CMS_TEXT,
        "cross_reference": _C.CMS_TEXT,
        "other_text": _C.CMS_TEXT,
        "transmittal_number": _C.REFERENCE,
        "transmittal_issued": _C.REFERENCE,
        "transmittal_url": _C.REFERENCE,
        "change_request_number": _C.REFERENCE,
        "publication_code": _C.REFERENCE,
        "revision_history": _C.CMS_TEXT,
        "under_review": _C.REFERENCE,
        "created_at": _C.REFERENCE,
        "last_updated_at": _C.REFERENCE,
        "last_cleared_at": _C.REFERENCE,
        "is_lab": _C.REFERENCE,
        "keywords": _C.CMS_TEXT,
    },
    "ncd_benefit_category": {
        "ncd_id": _C.REFERENCE,
        "version": _C.REFERENCE,
        "category_code": _C.REFERENCE,
    },
    "benefit_category": {"code": _C.REFERENCE, "description": _C.CMS_TEXT},
    "publication": {"code": _C.REFERENCE, "manual_number": _C.REFERENCE, "title": _C.CMS_TEXT},
}


def check_schema(
    connection: sqlite3.Connection,
    reviewed_columns: Mapping[str, Mapping[str, Classification]] = REVIEWED,
) -> list[str]:
    """List every way the database's schema breaks the licence rule.

    Args:
        connection: An open database. Only its schema is read.
        reviewed_columns: The classification to check against; `REVIEWED` unless testing.

    Returns:
        One message per violation; empty when the schema is clean.
    """
    violations: list[str] = []
    tables = [
        name
        for (name,) in connection.execute(
            "SELECT name FROM sqlite_schema WHERE type = 'table' AND name NOT LIKE 'sqlite_%' "
            "ORDER BY name"
        )
    ]
    for table in tables:
        reviewed = reviewed_columns.get(table)
        if reviewed is None:
            violations.append(f"table {table!r} has not been reviewed for licensed content")
            continue
        for column in _columns(connection, table):
            classification = reviewed.get(column)
            if classification is None:
                violations.append(f"column {table}.{column} has not been reviewed")
            elif classification is Classification.LICENSED:
                violations.append(f"column {table}.{column} holds licensed text")
    return violations


def withhold_reason(version: NcdVersion) -> str | None:
    """Say why an NCD version must be kept out of the store, or None if it may be stored.

    CMS sets its AMA flag on a document when the AMA copyright notice for CPT must be shown
    with it, which means its text may quote CPT descriptions. Such a document is withheld
    whole, because the description can sit anywhere in its prose. No NCD in the current
    download carries the flag.
    """
    if version.shows_ama_notice:
        return "withheld: CMS marks it as possibly containing CPT text"
    return None


def _columns(connection: sqlite3.Connection, table: str) -> list[str]:
    """Column names of one table, read from the schema rather than trusted from code."""
    # The name comes from sqlite_schema, not from input, and PRAGMA can't take a parameter.
    rows = connection.execute(f"PRAGMA table_info({_quoted(table)})").fetchall()
    return [str(row[1]) for row in rows]


def _quoted(identifier: str) -> str:
    """Quote an SQL identifier."""
    return '"' + identifier.replace('"', '""') + '"'
