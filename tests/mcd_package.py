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


#: The NCD tables' headers in the order and case CMS writes them.
NCD_TRKG_HEADER = (
    "NCD_id",
    "NCD_vrsn_num",
    "natl_cvrg_type",
    "cvrg_lvl_cd",
    "NCD_mnl_sect",
    "NCD_mnl_sect_title",
    "NCD_efctv_dt",
    "NCD_impltn_dt",
    "NCD_trmntn_dt",
    "itm_srvc_desc",
    "indctn_lmtn",
    "xref_txt",
    "othr_txt",
    "trnsmtl_num",
    "trnsmtl_issnc_dt",
    "trnsmtl_url",
    "chg_rqst_num",
    "pblctn_cd",
    "rev_hstry",
    "under_rvw",
    "creatd_tmstmp",
    "last_updt_tmstmp",
    "last_clrnc_tmstmp",
    "NCD_lab",
    "ncd_keyword",
    "NCD_AMA",
)
XREF_HEADER = ("NCD_id", "NCD_vrsn_num", "bnft_ctgry_cd", "creatd_tmstmp", "last_updt_tmstmp")


def ncd_row(**overrides: str) -> list[str]:
    """An invented, valid `ncd_trkg` row. Keyword arguments replace cells by lower-cased column."""
    values = {
        "ncd_id": "1",
        "ncd_vrsn_num": "1",
        "natl_cvrg_type": "True",
        "cvrg_lvl_cd": "2",
        "ncd_mnl_sect": "999.1",
        "ncd_mnl_sect_title": "Example Widget Therapy",
        "ncd_efctv_dt": "2020-01-01 00:00:00",
        "ncd_impltn_dt": "",
        "ncd_trmntn_dt": "",
        "itm_srvc_desc": "<p>An invented service.</p>",
        "indctn_lmtn": "<p>Covered when invented condition A is present.</p>",
        "xref_txt": "",
        "othr_txt": "",
        "trnsmtl_num": "1",
        "trnsmtl_issnc_dt": "2019-12-01 00:00:00",
        "trnsmtl_url": "https://example.invalid/r1.pdf",
        "chg_rqst_num": "",
        "pblctn_cd": "25",
        "rev_hstry": "",
        "under_rvw": "False",
        "creatd_tmstmp": "2019-11-27 12:10:46",
        "last_updt_tmstmp": "2019-11-28 09:00:00",
        "last_clrnc_tmstmp": "2019-11-29 10:30:15.550000",
        "ncd_lab": "False",
        "ncd_keyword": "",
        "ncd_ama": "False",
    }
    unknown = set(overrides) - set(values)
    if unknown:
        raise KeyError(f"no such ncd_trkg column: {sorted(unknown)}")
    values.update(overrides)
    return [values[column.lower()] for column in NCD_TRKG_HEADER]


def build_ncd_package(
    path: Path,
    versions: Sequence[Sequence[str]] | None = None,
    links: Sequence[Sequence[str]] | None = None,
    categories: Sequence[Sequence[str]] | None = None,
    publications: Sequence[Sequence[str]] | None = None,
) -> Path:
    """Write an NCD package; anything not given gets one consistent invented row."""
    stamp = "2019-11-27 12:10:46"
    return build_package(
        path,
        {
            "ncd_trkg": (NCD_TRKG_HEADER, versions if versions is not None else [ncd_row()]),
            "ncd_trkg_bnft_xref": (
                XREF_HEADER,
                links if links is not None else [["1", "1", "7", stamp, stamp]],
            ),
            "ncd_bnft_ctgry_ref": (
                ("bnft_ctgry_cd", "bnft_ctgry_desc"),
                categories if categories is not None else [["7", "Invented benefit"]],
            ),
            "ncd_pblctn_ref": (
                ("pblctn_cd", "pblctn_num", "pblctn_title"),
                publications if publications is not None else [["25", "100-03", "Invented manual"]],
            ),
        },
    )
