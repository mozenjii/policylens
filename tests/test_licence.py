"""The licence gate: nothing unreviewed or licensed gets into the database."""

import sqlite3
from dataclasses import replace
from pathlib import Path

from mcd_package import build_ncd_package
from policylens import licence
from policylens.ingest.ncd import NCD_TABLES, parse_ncd
from policylens.ingest.package import read_package


def database(*statements: str) -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:")
    for statement in statements:
        connection.execute(statement)
    return connection


def test_a_schema_of_reviewed_columns_passes() -> None:
    connection = database("CREATE TABLE benefit_category (code TEXT, description TEXT)")
    assert licence.check_schema(connection) == []


def test_an_unreviewed_table_fails() -> None:
    connection = database("CREATE TABLE lcd_code (code TEXT)")
    assert licence.check_schema(connection) == [
        "table 'lcd_code' has not been reviewed for licensed content"
    ]


def test_an_unreviewed_column_in_a_reviewed_table_fails() -> None:
    connection = database("CREATE TABLE benefit_category (code TEXT, long_description TEXT)")
    assert licence.check_schema(connection) == [
        "column benefit_category.long_description has not been reviewed"
    ]


def test_a_column_classified_as_licensed_fails() -> None:
    # The shape of the HCPCS code tables in the LCD and Article downloads, where CPT
    # descriptions live.
    reviewed = {
        "hcpc_code": {
            "code": licence.Classification.REFERENCE,
            "long_description": licence.Classification.LICENSED,
        }
    }
    connection = database("CREATE TABLE hcpc_code (code TEXT, long_description TEXT)")
    assert licence.check_schema(connection, reviewed) == [
        "column hcpc_code.long_description holds licensed text"
    ]


def test_an_odd_table_name_is_quoted_not_executed() -> None:
    connection = database('CREATE TABLE "x"")--" (a TEXT)')
    assert licence.check_schema(connection) == [
        "table 'x\")--' has not been reviewed for licensed content"
    ]


def test_a_document_flagged_for_the_ama_notice_is_withheld(tmp_path: Path) -> None:
    data = parse_ncd(read_package(build_ncd_package(tmp_path / "ncd.zip"), NCD_TABLES))
    version = data.versions[(1, 1)]
    assert licence.withhold_reason(version) is None
    flagged = replace(version, shows_ama_notice=True)
    assert licence.withhold_reason(flagged) == (
        "withheld: CMS marks it as possibly containing CPT text"
    )
