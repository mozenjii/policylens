"""Building the database: what it stores, what it refuses, and that a failure changes nothing."""

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from mcd_package import build_ncd_package, ncd_row
from policylens import licence
from policylens.ingest.ncd import NCD_TABLES, parse_ncd
from policylens.ingest.package import read_package
from policylens.store import build
from policylens.store.build import (
    BuildError,
    BuildSummary,
    SchemaVersionError,
    build_database,
    open_readonly,
    verify_database,
)
from policylens.store.schema import SCHEMA, SCHEMA_VERSION

NOW = datetime(2026, 11, 6, 12, 0, tzinfo=UTC)


def build_from(package_path: Path, target: Path) -> BuildSummary:
    package = read_package(package_path, NCD_TABLES)
    return build_database(package, parse_ncd(package), target, now=NOW)


def test_a_build_stores_versions_links_and_provenance(tmp_path: Path) -> None:
    rows = [ncd_row(), ncd_row(ncd_id="2", cvrg_lvl_cd="4")]
    summary = build_from(build_ncd_package(tmp_path / "ncd.zip", rows), tmp_path / "db.sqlite")
    assert (summary.stored, summary.withheld, summary.errors, summary.warnings) == (2, 0, 0, 1)

    with open_readonly(summary.path) as db:
        assert db.execute(
            "SELECT ncd_id, coverage_level, effective_date, implementation_date FROM ncd_version"
            " ORDER BY ncd_id"
        ).fetchall() == [(1, "restricted", "2020-01-01", None), (2, "unknown", "2020-01-01", None)]
        assert db.execute("SELECT * FROM ncd_benefit_category").fetchall() == [(1, 1, "7")]
        assert db.execute("SELECT package_sha256, built_at FROM snapshot").fetchone() == (
            summary.package_sha256,
            NOW.isoformat(),
        )
        assert db.execute(
            "SELECT table_name, row_number, severity FROM ingest_issue"
        ).fetchall() == [("ncd_trkg", 2, "warning")]


def test_a_document_flagged_for_cpt_text_is_withheld_with_its_links(tmp_path: Path) -> None:
    stamp = "2019-11-27 12:10:46"
    rows = [ncd_row(), ncd_row(ncd_id="2", ncd_ama="True")]
    links = [["1", "1", "7", stamp, stamp], ["2", "1", "7", stamp, stamp]]
    package = build_ncd_package(tmp_path / "ncd.zip", rows, links)
    summary = build_from(package, tmp_path / "db.sqlite")
    assert (summary.stored, summary.withheld) == (1, 1)
    with open_readonly(summary.path) as db:
        assert db.execute("SELECT ncd_id FROM ncd_version").fetchall() == [(1,)]
        assert db.execute("SELECT ncd_id FROM ncd_benefit_category").fetchall() == [(1,)]
        (message,) = db.execute(
            "SELECT message FROM ingest_issue WHERE row_number IS NULL"
        ).fetchone()
        assert message.startswith("NCD 2 version 1 withheld")


def test_the_built_schema_passes_the_licence_gate(tmp_path: Path) -> None:
    summary = build_from(build_ncd_package(tmp_path / "ncd.zip"), tmp_path / "db.sqlite")
    with open_readonly(summary.path) as db:
        assert licence.check_schema(db) == []


def test_a_build_that_fails_a_check_leaves_the_old_database_in_place(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "db.sqlite"
    target.write_bytes(b"the previous good build")

    def gate_finds_licensed_text(_: sqlite3.Connection) -> list[str]:
        return ["column x.y holds licensed text"]

    monkeypatch.setattr(build.licence, "check_schema", gate_finds_licensed_text)
    with pytest.raises(BuildError, match=r"licence gate: column x\.y"):
        build_from(build_ncd_package(tmp_path / "ncd.zip"), target)
    assert target.read_bytes() == b"the previous good build"
    assert not (tmp_path / "db.sqlite.building").exists()


def test_a_successful_build_replaces_the_previous_database(tmp_path: Path) -> None:
    target = tmp_path / "db.sqlite"
    target.write_bytes(b"the previous build")
    build_from(build_ncd_package(tmp_path / "ncd.zip"), target)
    with open_readonly(target) as db:
        assert db.execute("SELECT count(*) FROM ncd_version").fetchone() == (1,)


def test_the_read_only_connection_refuses_writes(tmp_path: Path) -> None:
    summary = build_from(build_ncd_package(tmp_path / "ncd.zip"), tmp_path / "db.sqlite")
    with open_readonly(summary.path) as db, pytest.raises(sqlite3.OperationalError):
        db.execute("DELETE FROM ncd_version")


def test_opening_a_missing_database_fails_rather_than_creating_one(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        open_readonly(tmp_path / "absent.sqlite")
    assert not (tmp_path / "absent.sqlite").exists()


def test_a_database_from_another_schema_version_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "old.sqlite"
    with sqlite3.connect(path) as db:
        db.execute(f"PRAGMA user_version = {SCHEMA_VERSION + 1}")
    with pytest.raises(SchemaVersionError, match="this code reads"):
        open_readonly(path)


def empty_database() -> sqlite3.Connection:
    db = sqlite3.connect(":memory:")
    db.executescript(SCHEMA)
    return db


def test_an_empty_database_passes_verification() -> None:
    verify_database(empty_database())


def test_verification_catches_a_link_to_a_missing_version() -> None:
    # The parser drops such links, so this guards against a future writer that doesn't.
    db = empty_database()
    db.execute("INSERT INTO ncd_benefit_category VALUES (99, 1, '7')")
    with pytest.raises(BuildError, match="foreign key check: 1 row"):
        verify_database(db)
