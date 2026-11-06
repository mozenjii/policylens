"""The database schema, and its version number.

Tables are STRICT so a value of the wrong type is an error at build time instead of a
surprise at query time. Dates are ISO-8601 text: SQLite has no date type, and ISO text sorts
and compares correctly as a string.

Every column here must also be classified in `policylens.licence.REVIEWED`; the build fails
if one isn't.
"""

from __future__ import annotations

#: Bump whenever the schema changes, so code can refuse a database it doesn't understand.
SCHEMA_VERSION = 1

SCHEMA = """
CREATE TABLE snapshot (
    package_sha256 TEXT PRIMARY KEY,
    dataset TEXT NOT NULL,
    package_name TEXT NOT NULL,
    built_at TEXT NOT NULL
) STRICT;

CREATE TABLE ingest_issue (
    dataset TEXT NOT NULL,
    table_name TEXT NOT NULL,
    row_number INTEGER,  -- NULL when the issue is about a document, not a CSV row
    column_name TEXT NOT NULL,
    severity TEXT NOT NULL CHECK (severity IN ('error', 'warning')),
    message TEXT NOT NULL
) STRICT;

CREATE TABLE publication (
    code TEXT PRIMARY KEY,
    manual_number TEXT NOT NULL,
    title TEXT NOT NULL
) STRICT;

CREATE TABLE benefit_category (
    code TEXT PRIMARY KEY,
    description TEXT NOT NULL
) STRICT;

CREATE TABLE ncd_version (
    ncd_id INTEGER NOT NULL,
    version INTEGER NOT NULL,
    is_ncd INTEGER NOT NULL CHECK (is_ncd IN (0, 1)),
    coverage_level TEXT NOT NULL
        CHECK (coverage_level IN ('full', 'restricted', 'none', 'unknown')),
    coverage_level_code TEXT NOT NULL,
    manual_section TEXT NOT NULL,
    manual_section_title TEXT NOT NULL,
    effective_date TEXT NOT NULL,
    implementation_date TEXT,
    termination_date TEXT,
    item_service_description TEXT,
    indications_limitations TEXT,
    cross_reference TEXT,
    other_text TEXT,
    transmittal_number TEXT,
    transmittal_issued TEXT,
    transmittal_url TEXT,
    change_request_number TEXT,
    publication_code TEXT NOT NULL,
    revision_history TEXT,
    under_review INTEGER NOT NULL CHECK (under_review IN (0, 1)),
    created_at TEXT NOT NULL,
    last_updated_at TEXT NOT NULL,
    last_cleared_at TEXT NOT NULL,
    is_lab INTEGER NOT NULL CHECK (is_lab IN (0, 1)),
    keywords TEXT,
    PRIMARY KEY (ncd_id, version)
) STRICT;

CREATE TABLE ncd_benefit_category (
    ncd_id INTEGER NOT NULL,
    version INTEGER NOT NULL,
    category_code TEXT NOT NULL,
    PRIMARY KEY (ncd_id, version, category_code),
    FOREIGN KEY (ncd_id, version) REFERENCES ncd_version (ncd_id, version)
) STRICT;

CREATE INDEX ncd_version_by_section ON ncd_version (manual_section);
"""
