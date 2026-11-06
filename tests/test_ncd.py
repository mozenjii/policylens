"""Parsing NCD tables: typed values, and what happens to every kind of bad row."""

from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from mcd_package import build_ncd_package, ncd_row
from policylens.ingest.ncd import NCD_TABLES, CoverageLevel, Issue, NcdData, Severity, parse_ncd
from policylens.ingest.package import read_package

STAMP = "2019-11-27 12:10:46"


def parse(path: Path) -> NcdData:
    return parse_ncd(read_package(path, NCD_TABLES))


def problems(data: NcdData) -> list[tuple[str, int, str, Severity]]:
    return [(i.table, i.row, i.column, i.severity) for i in data.issues]


def test_a_clean_package_parses_into_typed_values(tmp_path: Path) -> None:
    data = parse(build_ncd_package(tmp_path / "ncd.zip"))
    assert data.issues == ()
    version = data.versions[(1, 1)]
    assert version.coverage_level is CoverageLevel.RESTRICTED
    assert version.effective_date == date(2020, 1, 1)
    assert version.implementation_date is None
    assert version.cross_reference is None
    assert version.indications_limitations == "<p>Covered when invented condition A is present.</p>"
    assert version.last_cleared_at == datetime(2019, 11, 29, 10, 30, 15, 550000, tzinfo=UTC)
    assert version.is_ncd and not version.under_review and not version.shows_ama_notice
    assert data.benefit_categories == {"7": "Invented benefit"}
    assert data.publications == {"25": ("100-03", "Invented manual")}
    assert data.version_benefits == ((1, 1, "7"),)


@pytest.mark.parametrize(
    ("code", "level"),
    [("1", CoverageLevel.FULL), ("2", CoverageLevel.RESTRICTED), ("3", CoverageLevel.NONE)],
)
def test_each_defined_coverage_level_maps_to_its_meaning(
    tmp_path: Path, code: str, level: CoverageLevel
) -> None:
    data = parse(build_ncd_package(tmp_path / "ncd.zip", [ncd_row(cvrg_lvl_cd=code)]))
    assert data.versions[(1, 1)].coverage_level is level


def test_an_undefined_coverage_level_is_kept_as_unknown_with_its_code(tmp_path: Path) -> None:
    # CMS ships a level 4 that the data dictionary doesn't define. Guessing its meaning could
    # turn "unknown" into "covered", so it stays unknown and is reported.
    data = parse(build_ncd_package(tmp_path / "ncd.zip", [ncd_row(cvrg_lvl_cd="4")]))
    version = data.versions[(1, 1)]
    assert (version.coverage_level, version.coverage_level_code) == (CoverageLevel.UNKNOWN, "4")
    assert problems(data) == [("ncd_trkg", 1, "cvrg_lvl_cd", Severity.WARNING)]


def test_last_changed_is_the_later_of_updated_and_cleared(tmp_path: Path) -> None:
    rows = [
        ncd_row(last_updt_tmstmp="2024-05-01 00:00:00", last_clrnc_tmstmp="2024-04-01 00:00:00")
    ]
    version = parse(build_ncd_package(tmp_path / "ncd.zip", rows)).versions[(1, 1)]
    assert version.last_changed_at == datetime(2024, 5, 1, tzinfo=UTC)


@pytest.mark.parametrize(
    ("override", "column"),
    [
        ({"ncd_efctv_dt": ""}, "ncd_efctv_dt"),
        ({"ncd_efctv_dt": "1st of May"}, "ncd_efctv_dt"),
        ({"ncd_id": "A12"}, "ncd_id"),
        ({"under_rvw": "yes"}, "under_rvw"),
        ({"ncd_mnl_sect": "  "}, "ncd_mnl_sect"),
        ({"creatd_tmstmp": ""}, "creatd_tmstmp"),
    ],
)
def test_a_row_that_breaks_the_dictionary_is_dropped_and_reported(
    tmp_path: Path, override: dict[str, str], column: str
) -> None:
    rows = [ncd_row(**override), ncd_row(ncd_id="2")]
    links = [["2", "1", "7", STAMP, STAMP]]
    data = parse(build_ncd_package(tmp_path / "ncd.zip", rows, links))
    assert set(data.versions) == {(2, 1)}
    assert problems(data) == [("ncd_trkg", 1, column, Severity.ERROR)]


def test_a_duplicate_version_keeps_the_first_and_reports_the_second(tmp_path: Path) -> None:
    rows = [ncd_row(ncd_mnl_sect="1.1"), ncd_row(ncd_mnl_sect="1.2")]
    data = parse(build_ncd_package(tmp_path / "ncd.zip", rows))
    assert data.versions[(1, 1)].manual_section == "1.1"
    assert problems(data) == [("ncd_trkg", 2, "", Severity.ERROR)]


def test_a_link_to_a_version_that_was_not_loaded_is_dropped(tmp_path: Path) -> None:
    links = [["1", "1", "7", STAMP, STAMP], ["9", "1", "7", STAMP, STAMP]]
    data = parse(build_ncd_package(tmp_path / "ncd.zip", links=links))
    assert data.version_benefits == ((1, 1, "7"),)
    assert problems(data) == [("ncd_trkg_bnft_xref", 2, "", Severity.ERROR)]


def test_a_duplicate_link_is_dropped(tmp_path: Path) -> None:
    link = ["1", "1", "7", STAMP, STAMP]
    data = parse(build_ncd_package(tmp_path / "ncd.zip", links=[link, link]))
    assert data.version_benefits == ((1, 1, "7"),)
    assert problems(data) == [("ncd_trkg_bnft_xref", 2, "", Severity.ERROR)]


def test_a_link_with_a_bad_value_is_dropped(tmp_path: Path) -> None:
    data = parse(build_ncd_package(tmp_path / "ncd.zip", links=[["1", "one", "7", STAMP, STAMP]]))
    assert data.version_benefits == ()
    assert problems(data) == [("ncd_trkg_bnft_xref", 1, "ncd_vrsn_num", Severity.ERROR)]


def test_an_unknown_benefit_category_is_kept_and_reported(tmp_path: Path) -> None:
    data = parse(build_ncd_package(tmp_path / "ncd.zip", links=[["1", "1", "99", STAMP, STAMP]]))
    assert data.version_benefits == ((1, 1, "99"),)
    assert problems(data) == [("ncd_trkg_bnft_xref", 1, "bnft_ctgry_cd", Severity.WARNING)]


def test_an_unknown_publication_is_kept_and_reported(tmp_path: Path) -> None:
    data = parse(build_ncd_package(tmp_path / "ncd.zip", [ncd_row(pblctn_cd="77")]))
    assert (1, 1) in data.versions
    assert problems(data) == [("ncd_trkg", 1, "pblctn_cd", Severity.WARNING)]


def test_duplicate_and_empty_reference_codes_are_dropped(tmp_path: Path) -> None:
    categories = [["7", "Invented benefit"], ["7", "Again"], ["", "No code"]]
    data = parse(build_ncd_package(tmp_path / "ncd.zip", categories=categories))
    assert data.benefit_categories == {"7": "Invented benefit"}
    assert problems(data) == [
        ("ncd_bnft_ctgry_ref", 2, "bnft_ctgry_cd", Severity.ERROR),
        ("ncd_bnft_ctgry_ref", 3, "bnft_ctgry_cd", Severity.ERROR),
    ]


def test_issues_say_what_was_wrong(tmp_path: Path) -> None:
    rows = [ncd_row(ncd_efctv_dt="soon")]
    data = parse(build_ncd_package(tmp_path / "ncd.zip", rows, links=[]))
    (issue,) = data.issues
    assert issue == Issue(
        "ncd_trkg", 1, "ncd_efctv_dt", Severity.ERROR, "expected a date or timestamp, got 'soon'"
    )
