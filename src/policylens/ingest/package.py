"""Open one MCD download package and return its CSV tables, checked against the expected columns.

A package is the ZIP that CMS publishes (for example `ncd.zip`). It holds an Access database, a
PDF data dictionary, a readme and an inner `*_csv.zip` with one CSV per table. Only the CSVs
are read.

The column check is exact on purpose. A column CMS adds might be a new licensed descriptor,
and a column it drops might be one the coverage logic depends on. Either way the right
response is to stop and have a person look, not to carry on with a guess.

Deliberate boundary: this module knows the package's shape, not what any column means.
Turning strings into typed values is the job of the per-dataset parsers.
"""

from __future__ import annotations

import csv
import hashlib
import io
import zipfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

#: Refuse any archive member larger than this once uncompressed. The real packages are tens
#: of megabytes; the limit exists so a corrupt or hostile ZIP can't exhaust memory.
MAX_MEMBER_BYTES = 512 * 1024 * 1024


class PackageError(Exception):
    """The package can't be used as it stands. The message says which file and why."""


@dataclass(frozen=True, slots=True)
class Row:
    """One CSV record.

    Attributes:
        number: 1-based position among the table's data rows, for error messages. Not a
            physical line number: quoted fields span lines.
        values: Cell text keyed by lower-cased column name. Empty cells are empty strings.
    """

    number: int
    values: Mapping[str, str]


@dataclass(frozen=True, slots=True)
class Table:
    """One CSV table from the package.

    Attributes:
        name: Lower-cased table name, the CSV file name without `.csv`.
        rows: Data rows, in file order.
    """

    name: str
    rows: tuple[Row, ...]


@dataclass(frozen=True, slots=True)
class Package:
    """A package that opened cleanly and has every expected table with exactly its columns.

    Attributes:
        path: Where the package was read from.
        sha256: Hex digest of the package file, which identifies the snapshot it came from.
        tables: Tables by lower-cased name.
    """

    path: Path
    sha256: str
    tables: Mapping[str, Table]


def read_package(path: Path, expected: Mapping[str, frozenset[str]]) -> Package:
    """Open a package and read the expected tables.

    Args:
        path: The package ZIP.
        expected: Lower-cased table name to the exact set of lower-cased column names.

    Returns:
        The package with exactly the expected tables.

    Raises:
        PackageError: If the file isn't a ZIP, has no single inner CSV archive, lacks a table,
            a table's columns differ from the expected set, a member is too large, or a CSV
            isn't UTF-8.
    """
    data = path.read_bytes()
    try:
        outer = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as error:
        raise PackageError(f"{path.name}: not a ZIP file") from error

    inner = zipfile.ZipFile(io.BytesIO(_read_member(outer, _inner_archive_name(outer, path))))
    members = {Path(name).name.lower(): name for name in inner.namelist()}

    tables: dict[str, Table] = {}
    for table, columns in sorted(expected.items()):
        member = members.get(f"{table}.csv")
        if member is None:
            raise PackageError(f"{path.name}: no {table}.csv in the CSV archive")
        tables[table] = _read_table(table, _read_member(inner, member), columns)
    return Package(path=path, sha256=hashlib.sha256(data).hexdigest(), tables=tables)


def _inner_archive_name(outer: zipfile.ZipFile, path: Path) -> str:
    """Find the single `*_csv.zip` member of the outer package."""
    candidates = [name for name in outer.namelist() if name.lower().endswith("_csv.zip")]
    if len(candidates) != 1:
        raise PackageError(f"{path.name}: expected one *_csv.zip inside, found {len(candidates)}")
    return candidates[0]


def _read_member(archive: zipfile.ZipFile, name: str) -> bytes:
    """Read one archive member, refusing it if it would decompress past the size limit."""
    if archive.getinfo(name).file_size > MAX_MEMBER_BYTES:
        raise PackageError(f"{name}: larger than {MAX_MEMBER_BYTES} bytes uncompressed")
    return archive.read(name)


def _read_table(name: str, raw: bytes, expected: frozenset[str]) -> Table:
    """Decode and parse one CSV, then check its header against the expected columns."""
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise PackageError(
            f"{name}.csv: not UTF-8 ({error.reason} at byte {error.start})"
        ) from error

    reader = csv.reader(io.StringIO(text, newline=""))
    no_header: list[str] = []
    header = [column.strip().lower() for column in next(reader, no_header)]
    duplicated = sorted({column for column in header if header.count(column) > 1})
    if duplicated:
        raise PackageError(f"{name}.csv: columns duplicated: {', '.join(duplicated)}")
    missing = sorted(expected - set(header))
    unexpected = sorted(set(header) - expected)
    if missing or unexpected:
        raise PackageError(
            f"{name}.csv: columns differ from the data dictionary "
            f"(missing: {missing or 'none'}; unexpected: {unexpected or 'none'})"
        )

    rows: list[Row] = []
    for number, cells in enumerate(reader, start=1):
        if len(cells) != len(header):
            raise PackageError(
                f"{name}.csv row {number}: {len(cells)} cells, header has {len(header)}"
            )
        rows.append(Row(number=number, values=dict(zip(header, cells, strict=True))))
    return Table(name=name, rows=tuple(rows))
