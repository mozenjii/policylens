"""Reading a download package: the happy path, and every way it refuses a package."""

import hashlib
import zipfile
from pathlib import Path

import pytest

from mcd_package import build_package
from policylens.ingest import package
from policylens.ingest.package import PackageError, read_package

EXPECTED = {"widget": frozenset({"id", "name"})}


def test_reads_tables_with_lowercased_columns_and_row_numbers(tmp_path: Path) -> None:
    path = build_package(
        tmp_path / "p.zip",
        {"Widget": (["ID", "Name"], [["1", "first, with a comma"], ["2", "two\nlines"]])},
    )
    result = read_package(path, EXPECTED)
    rows = result.tables["widget"].rows
    assert [row.number for row in rows] == [1, 2]
    assert rows[0].values == {"id": "1", "name": "first, with a comma"}
    assert rows[1].values["name"] == "two\nlines"
    assert result.sha256 == hashlib.sha256(path.read_bytes()).hexdigest()


def test_extra_tables_in_the_archive_are_ignored(tmp_path: Path) -> None:
    path = build_package(
        tmp_path / "p.zip",
        {"widget": (["id", "name"], []), "unused": (["x"], [["1"]])},
    )
    assert set(read_package(path, EXPECTED).tables) == {"widget"}


def test_a_file_that_is_not_a_zip_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "p.zip"
    path.write_bytes(b"not a zip")
    with pytest.raises(PackageError, match="not a ZIP"):
        read_package(path, EXPECTED)


def test_a_package_without_one_inner_csv_archive_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "p.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("readme_first.txt", "nothing else")
    with pytest.raises(PackageError, match="expected one"):
        read_package(path, EXPECTED)


def test_a_missing_table_is_refused(tmp_path: Path) -> None:
    path = build_package(tmp_path / "p.zip", {"other": (["id"], [])})
    with pytest.raises(PackageError, match=r"no widget\.csv"):
        read_package(path, EXPECTED)


@pytest.mark.parametrize(
    ("header", "message"),
    [
        (["id"], r"missing: \['name'\]"),
        (["id", "name", "long_description"], r"unexpected: \['long_description'\]"),
        (["id", "name", "name"], "duplicated: name"),
    ],
)
def test_columns_must_match_the_dictionary_exactly(
    tmp_path: Path, header: list[str], message: str
) -> None:
    path = build_package(tmp_path / "p.zip", {"widget": (header, [])})
    with pytest.raises(PackageError, match=message):
        read_package(path, EXPECTED)


def test_a_row_with_the_wrong_number_of_cells_is_refused(tmp_path: Path) -> None:
    path = build_package(tmp_path / "p.zip", {"widget": (["id", "name"], [["1", "a", "extra"]])})
    with pytest.raises(PackageError, match="row 1: 3 cells"):
        read_package(path, EXPECTED)


def test_a_table_that_is_not_utf8_is_refused(tmp_path: Path) -> None:
    path = build_package(
        tmp_path / "p.zip", {}, raw_members={"widget.csv": b"id,name\r\n1,\xff\r\n"}
    )
    with pytest.raises(PackageError, match="not UTF-8"):
        read_package(path, EXPECTED)


def test_an_oversized_member_is_refused_before_it_is_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = build_package(tmp_path / "p.zip", {"widget": (["id", "name"], [["1", "a"]])})
    monkeypatch.setattr(package, "MAX_MEMBER_BYTES", 10)
    with pytest.raises(PackageError, match="larger than 10 bytes"):
        read_package(path, EXPECTED)
