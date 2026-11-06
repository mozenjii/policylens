"""Build small, made-up MCD download packages for tests.

The real packages carry licensed and copyrighted text, so none of it is committed. These
helpers write the same container shape (an outer ZIP holding an inner `*_csv.zip` of CSVs)
around invented rows.
"""

from __future__ import annotations

import csv
import io
import zipfile
from collections.abc import Mapping, Sequence
from pathlib import Path

#: A table as written: its header, then rows of cells in header order.
CsvTable = tuple[Sequence[str], Sequence[Sequence[str]]]


def csv_bytes(header: Sequence[str], rows: Sequence[Sequence[str]]) -> bytes:
    """Encode a table the way CMS does: comma separated, double-quoted, CRLF line ends."""
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, quoting=csv.QUOTE_MINIMAL, lineterminator="\r\n")
    writer.writerow(header)
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


def build_package(
    path: Path,
    tables: Mapping[str, CsvTable],
    *,
    inner_name: str = "ncd_csv.zip",
    raw_members: Mapping[str, bytes] | None = None,
) -> Path:
    """Write a package ZIP to `path` and return it.

    Args:
        path: Where to write the package.
        tables: CSV file stem to its header and rows.
        inner_name: Name of the inner CSV archive.
        raw_members: Extra inner-archive members written byte for byte, for malformed cases.
    """
    inner = io.BytesIO()
    with zipfile.ZipFile(inner, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, (header, rows) in tables.items():
            archive.writestr(f"{name}.csv", csv_bytes(header, rows))
        for name, raw in (raw_members or {}).items():
            archive.writestr(name, raw)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as outer:
        outer.writestr("readme_first.txt", "made up for tests")
        outer.writestr(inner_name, inner.getvalue())
    return path
