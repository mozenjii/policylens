"""Parse the National Coverage Determination tables into typed, immutable records.

Source: the NCD data dictionary that ships inside the CMS `ncd.zip` package. Four tables:
`ncd_trkg` (one row per NCD version), `ncd_trkg_bnft_xref` (benefit categories per version),
`ncd_bnft_ctgry_ref` and `ncd_pblctn_ref` (reference lists).

How problems are handled, because it decides what the rest of the system can trust:

- A row that breaks the dictionary (a required value missing, a date that isn't a date, a
  duplicated key, a reference to a version that doesn't exist) is **dropped** and recorded as
  an error. Nothing downstream ever sees half a row.
- A row with a value the dictionary doesn't define but that doesn't make the row unusable is
  **kept** and recorded as a warning. The coverage level is the case that exists today: CMS
  ships a level `4` that the dictionary doesn't list. It becomes `CoverageLevel.UNKNOWN` with
  the raw code preserved, never a guess at the nearest defined level.

Every issue names the table, the row and the column, so the ingest report can say exactly
what was left out.

Deliberate boundary: text fields are kept exactly as CMS wrote them, HTML included. Turning
them into searchable, citable passages is retrieval's job.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from enum import StrEnum

from policylens.ingest.package import Package, Row

#: Table name to its exact columns, lower-cased, from the data dictionary.
NCD_TABLES: Mapping[str, frozenset[str]] = {
    "ncd_trkg": frozenset(
        {
            "ncd_id",
            "ncd_vrsn_num",
            "natl_cvrg_type",
            "cvrg_lvl_cd",
            "ncd_mnl_sect",
            "ncd_mnl_sect_title",
            "ncd_efctv_dt",
            "ncd_impltn_dt",
            "ncd_trmntn_dt",
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
            "ncd_lab",
            "ncd_keyword",
            "ncd_ama",
        }
    ),
    "ncd_trkg_bnft_xref": frozenset(
        {"ncd_id", "ncd_vrsn_num", "bnft_ctgry_cd", "creatd_tmstmp", "last_updt_tmstmp"}
    ),
    "ncd_bnft_ctgry_ref": frozenset({"bnft_ctgry_cd", "bnft_ctgry_desc"}),
    "ncd_pblctn_ref": frozenset({"pblctn_cd", "pblctn_num", "pblctn_title"}),
}


class CoverageLevel(StrEnum):
    """What an NCD says about coverage overall, from `cvrg_lvl_cd`."""

    FULL = "full"
    """Code 1: full coverage."""
    RESTRICTED = "restricted"
    """Code 2: covered only under the conditions the NCD states."""
    NONE = "none"
    """Code 3: not covered."""
    UNKNOWN = "unknown"
    """Any code the dictionary doesn't define. The raw code is kept beside it."""


_LEVELS = {"1": CoverageLevel.FULL, "2": CoverageLevel.RESTRICTED, "3": CoverageLevel.NONE}


class Severity(StrEnum):
    """Whether an issue cost us the row."""

    ERROR = "error"
    """The row was dropped."""
    WARNING = "warning"
    """The row was kept; something in it is not what the dictionary says."""


@dataclass(frozen=True, slots=True)
class Issue:
    """One problem found while parsing.

    Attributes:
        table: Lower-cased table name.
        row: 1-based data row number within the table.
        column: The column at fault, or empty when the problem is the row as a whole.
        severity: Whether the row was dropped.
        message: What was wrong, specific enough to find and fix.
    """

    table: str
    row: int
    column: str
    severity: Severity
    message: str


@dataclass(frozen=True, slots=True)
class NcdVersion:
    """One version of one NCD, as CMS published it.

    Text fields hold CMS's HTML as-is, or `None` when the field is empty.

    Attributes:
        ncd_id: CMS's document id.
        version: CMS's version number for this document.
        is_ncd: True for an NCD, False for a "coverage provision" in the manual.
        coverage_level: Overall coverage, or UNKNOWN for a code the dictionary doesn't define.
        coverage_level_code: The raw `cvrg_lvl_cd`, kept so an UNKNOWN can be traced.
        manual_section: Section number in the NCD Manual, such as "220.6".
        manual_section_title: The section's title.
        effective_date: The date this version takes effect.
        implementation_date: The date it is implemented, if given.
        termination_date: The date it stops being in effect, if any.
        item_service_description: What the item or service is.
        indications_limitations: When it is covered, and the limits on that.
        cross_reference: Pointers to related manual sections.
        other_text: Anything not in the fields above.
        transmittal_number: The transmittal that issued this version.
        transmittal_issued: When that transmittal was issued.
        transmittal_url: Link to the transmittal on cms.gov.
        change_request_number: The CMS change request behind it.
        publication_code: Key into the publication reference table.
        revision_history: CMS's description of what changed and when.
        under_review: Whether CMS has the NCD under review.
        created_at: When CMS created this version (UTC).
        last_updated_at: When CMS last updated it (UTC).
        last_cleared_at: When CMS last approved it for publication (UTC).
        is_lab: Whether it is a laboratory NCD.
        keywords: CMS's search keywords, if any.
        shows_ama_notice: Whether CMS displays the AMA copyright notice for it, which means its
            text may contain CPT content.
    """

    ncd_id: int
    version: int
    is_ncd: bool
    coverage_level: CoverageLevel
    coverage_level_code: str
    manual_section: str
    manual_section_title: str
    effective_date: date
    implementation_date: date | None
    termination_date: date | None
    item_service_description: str | None
    indications_limitations: str | None
    cross_reference: str | None
    other_text: str | None
    transmittal_number: str | None
    transmittal_issued: date | None
    transmittal_url: str | None
    change_request_number: str | None
    publication_code: str
    revision_history: str | None
    under_review: bool
    created_at: datetime
    last_updated_at: datetime
    last_cleared_at: datetime
    is_lab: bool
    keywords: str | None
    shows_ama_notice: bool

    @property
    def last_changed_at(self) -> datetime:
        """The most recent change: the dictionary defines it as the later of updated and cleared."""
        return max(self.last_updated_at, self.last_cleared_at)


@dataclass(frozen=True, slots=True)
class NcdData:
    """Everything parsed from one NCD package.

    Attributes:
        versions: NCD versions that parsed cleanly, keyed by `(ncd_id, version)`.
        benefit_categories: Benefit category code to its description.
        publications: Publication code to `(manual number, title)`.
        version_benefits: `(ncd_id, version, benefit category code)` links.
        issues: Every problem found, in the order found.
    """

    versions: Mapping[tuple[int, int], NcdVersion]
    benefit_categories: Mapping[str, str]
    publications: Mapping[str, tuple[str, str]]
    version_benefits: tuple[tuple[int, int, str], ...]
    issues: tuple[Issue, ...]


class _RowError(Exception):
    """A value in one column made the row unusable."""

    def __init__(self, column: str, message: str) -> None:
        super().__init__(message)
        self.column = column
        self.message = message


class _Fields:
    """Typed access to one row's cells. Each accessor raises `_RowError` on a bad value."""

    def __init__(self, row: Row) -> None:
        self._values = row.values

    def text(self, column: str) -> str | None:
        """The cell, or None if empty. Leading and trailing whitespace counts as empty only."""
        value = self._values[column]
        return value if value.strip() else None

    def required(self, column: str) -> str:
        """The cell, which must not be empty."""
        value = self.text(column)
        if value is None:
            raise _RowError(column, "required by the data dictionary but empty")
        return value

    def integer(self, column: str) -> int:
        """A required non-negative whole number."""
        value = self.required(column).strip()
        if not value.isdigit():
            raise _RowError(column, f"expected a whole number, got {value!r}")
        return int(value)

    def boolean(self, column: str) -> bool:
        """A required `True` or `False`, exactly as CMS writes them."""
        value = self.required(column).strip()
        if value not in {"True", "False"}:
            raise _RowError(column, f"expected True or False, got {value!r}")
        return value == "True"

    def day(self, column: str) -> date | None:
        """An optional date. CMS writes dates as timestamps at midnight."""
        moment = self.moment(column)
        return None if moment is None else moment.date()

    def required_day(self, column: str) -> date:
        """A required date."""
        value = self.day(column)
        if value is None:
            raise _RowError(column, "required by the data dictionary but empty")
        return value

    def moment(self, column: str) -> datetime | None:
        """An optional timestamp, which the dictionary says is UTC."""
        value = self.text(column)
        if value is None:
            return None
        for layout in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                return datetime.strptime(value.strip(), layout).replace(tzinfo=UTC)
            except ValueError:
                continue
        raise _RowError(column, f"expected a date or timestamp, got {value!r}")

    def required_moment(self, column: str) -> datetime:
        """A required timestamp."""
        value = self.moment(column)
        if value is None:
            raise _RowError(column, "required by the data dictionary but empty")
        return value


def parse_ncd(package: Package) -> NcdData:
    """Parse an NCD package that `read_package` has already checked against `NCD_TABLES`.

    Args:
        package: The package, with all four NCD tables present.

    Returns:
        The parsed data, with every dropped row and every oddity listed in `issues`.
    """
    issues: list[Issue] = []

    categories = _reference(package, "ncd_bnft_ctgry_ref", "bnft_ctgry_cd", issues, _category)
    publications = _reference(package, "ncd_pblctn_ref", "pblctn_cd", issues, _publication)

    versions: dict[tuple[int, int], NcdVersion] = {}
    for row in package.tables["ncd_trkg"].rows:
        version = _guarded(row, "ncd_trkg", issues, _version)
        if version is None:
            continue
        key = (version.ncd_id, version.version)
        if key in versions:
            issues.append(
                _issue("ncd_trkg", row, "", Severity.ERROR, f"duplicate NCD version {key}")
            )
            continue
        if version.coverage_level is CoverageLevel.UNKNOWN:
            message = f"coverage level {version.coverage_level_code!r} isn't in the data dictionary"
            issues.append(_issue("ncd_trkg", row, "cvrg_lvl_cd", Severity.WARNING, message))
        if version.publication_code not in publications:
            message = f"publication {version.publication_code!r} isn't in ncd_pblctn_ref"
            issues.append(_issue("ncd_trkg", row, "pblctn_cd", Severity.WARNING, message))
        versions[key] = version

    links = _benefit_links(package, versions, categories, issues)
    return NcdData(
        versions=versions,
        benefit_categories=categories,
        publications=publications,
        version_benefits=links,
        issues=tuple(issues),
    )


def _version(fields: _Fields) -> NcdVersion:
    """Build one NCD version from its row."""
    code = fields.required("cvrg_lvl_cd").strip()
    return NcdVersion(
        ncd_id=fields.integer("ncd_id"),
        version=fields.integer("ncd_vrsn_num"),
        is_ncd=fields.boolean("natl_cvrg_type"),
        coverage_level=_LEVELS.get(code, CoverageLevel.UNKNOWN),
        coverage_level_code=code,
        manual_section=fields.required("ncd_mnl_sect").strip(),
        manual_section_title=fields.required("ncd_mnl_sect_title").strip(),
        effective_date=fields.required_day("ncd_efctv_dt"),
        implementation_date=fields.day("ncd_impltn_dt"),
        termination_date=fields.day("ncd_trmntn_dt"),
        item_service_description=fields.text("itm_srvc_desc"),
        indications_limitations=fields.text("indctn_lmtn"),
        cross_reference=fields.text("xref_txt"),
        other_text=fields.text("othr_txt"),
        transmittal_number=fields.text("trnsmtl_num"),
        transmittal_issued=fields.day("trnsmtl_issnc_dt"),
        transmittal_url=fields.text("trnsmtl_url"),
        change_request_number=fields.text("chg_rqst_num"),
        publication_code=fields.required("pblctn_cd").strip(),
        revision_history=fields.text("rev_hstry"),
        under_review=fields.boolean("under_rvw"),
        created_at=fields.required_moment("creatd_tmstmp"),
        last_updated_at=fields.required_moment("last_updt_tmstmp"),
        last_cleared_at=fields.required_moment("last_clrnc_tmstmp"),
        is_lab=fields.boolean("ncd_lab"),
        keywords=fields.text("ncd_keyword"),
        shows_ama_notice=fields.boolean("ncd_ama"),
    )


def _category(fields: _Fields) -> tuple[str, str]:
    """A benefit category row as `(code, description)`."""
    return fields.required("bnft_ctgry_cd").strip(), fields.required("bnft_ctgry_desc").strip()


def _publication(fields: _Fields) -> tuple[str, tuple[str, str]]:
    """A publication row as `(code, (manual number, title))`."""
    code = fields.required("pblctn_cd").strip()
    return code, (fields.required("pblctn_num").strip(), fields.required("pblctn_title").strip())


def _reference[V](
    package: Package,
    table: str,
    key_column: str,
    issues: list[Issue],
    build: Callable[[_Fields], tuple[str, V]],
) -> dict[str, V]:
    """Parse a code-to-value reference table, dropping duplicate codes as errors."""
    result: dict[str, V] = {}
    for row in package.tables[table].rows:
        parsed = _guarded(row, table, issues, build)
        if parsed is None:
            continue
        code, value = parsed
        if code in result:
            issues.append(
                _issue(table, row, key_column, Severity.ERROR, f"duplicate code {code!r}")
            )
            continue
        result[code] = value
    return result


def _benefit_links(
    package: Package,
    versions: Mapping[tuple[int, int], NcdVersion],
    categories: Mapping[str, str],
    issues: list[Issue],
) -> tuple[tuple[int, int, str], ...]:
    """Parse the version-to-benefit-category links, dropping any that point at nothing."""
    table = "ncd_trkg_bnft_xref"
    links: list[tuple[int, int, str]] = []
    seen: set[tuple[int, int, str]] = set()
    for row in package.tables[table].rows:
        link = _guarded(row, table, issues, _link)
        if link is None:
            continue
        if link[:2] not in versions:
            message = f"links to NCD version {link[:2]}, which wasn't loaded"
            issues.append(_issue(table, row, "", Severity.ERROR, message))
            continue
        if link in seen:
            issues.append(_issue(table, row, "", Severity.ERROR, f"duplicate link {link}"))
            continue
        if link[2] not in categories:
            message = f"benefit category {link[2]!r} isn't in ncd_bnft_ctgry_ref"
            issues.append(_issue(table, row, "bnft_ctgry_cd", Severity.WARNING, message))
        seen.add(link)
        links.append(link)
    return tuple(links)


def _link(fields: _Fields) -> tuple[int, int, str]:
    """A benefit link row as `(ncd_id, version, category code)`."""
    return (
        fields.integer("ncd_id"),
        fields.integer("ncd_vrsn_num"),
        fields.required("bnft_ctgry_cd").strip(),
    )


def _guarded[T](
    row: Row, table: str, issues: list[Issue], build: Callable[[_Fields], T]
) -> T | None:
    """Run a row builder; on a bad value, record an error and return None so the row is dropped."""
    try:
        return build(_Fields(row))
    except _RowError as error:
        issues.append(_issue(table, row, error.column, Severity.ERROR, error.message))
        return None


def _issue(table: str, row: Row, column: str, severity: Severity, message: str) -> Issue:
    """Build an issue for one row."""
    return Issue(table=table, row=row.number, column=column, severity=severity, message=message)
