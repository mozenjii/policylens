"""The command line: exit codes and what it tells the person running it."""

from pathlib import Path

import pytest

from mcd_package import build_ncd_package, ncd_row
from policylens import cli
from policylens.store.build import open_readonly


def run(capsys: pytest.CaptureFixture[str], *argv: str) -> tuple[int, str]:
    code = cli.main(list(argv))
    return code, capsys.readouterr().out


def test_ingest_builds_the_database_and_reports_it(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    package = build_ncd_package(tmp_path / "ncd.zip", [ncd_row(cvrg_lvl_cd="4")])
    out = tmp_path / "db.sqlite"
    code, output = run(capsys, "ingest-ncd", str(package), "--out", str(out))
    assert code == 0
    assert "warning ncd_trkg row 1 cvrg_lvl_cd: coverage level '4'" in output
    assert "1 NCD version(s) stored, 0 withheld, 0 row(s) dropped, 1 warning(s)" in output
    with open_readonly(out) as db:
        assert db.execute("SELECT count(*) FROM ncd_version").fetchone() == (1,)


def test_dropped_rows_stop_the_build_by_default(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rows = [ncd_row(), ncd_row(ncd_id="2", ncd_efctv_dt="")]
    package = build_ncd_package(tmp_path / "ncd.zip", rows)
    out = tmp_path / "db.sqlite"
    code, output = run(capsys, "ingest-ncd", str(package), "--out", str(out))
    assert code == 1
    assert "1 row(s) dropped; database not built" in output
    assert not out.exists()


def test_dropped_rows_can_be_allowed_explicitly(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rows = [ncd_row(), ncd_row(ncd_id="2", ncd_efctv_dt="")]
    package = build_ncd_package(tmp_path / "ncd.zip", rows)
    out = tmp_path / "db.sqlite"
    code, output = run(
        capsys, "ingest-ncd", str(package), "--out", str(out), "--allow-dropped-rows"
    )
    assert code == 0
    assert "1 row(s) dropped" in output
    assert out.exists()


def test_an_unreadable_package_exits_2(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code, output = run(capsys, "ingest-ncd", str(tmp_path / "missing.zip"))
    assert code == 2
    assert "cannot read" in output


def test_a_refused_build_exits_2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    def refuse(*_: object, **__: object) -> object:
        raise cli.BuildError("licence gate: column x.y holds licensed text")

    monkeypatch.setattr(cli, "build_database", refuse)
    package = build_ncd_package(tmp_path / "ncd.zip")
    code, output = run(capsys, "ingest-ncd", str(package), "--out", str(tmp_path / "db.sqlite"))
    assert code == 2
    assert "build refused: licence gate" in output


def test_a_long_issue_list_is_capped(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    rows = [ncd_row(ncd_id=str(n), cvrg_lvl_cd="4") for n in range(1, cli.SHOWN_ISSUES + 4)]
    package = build_ncd_package(tmp_path / "ncd.zip", rows, links=[])
    _, output = run(capsys, "ingest-ncd", str(package), "--out", str(tmp_path / "db.sqlite"))
    assert output.count("warning ncd_trkg") == cli.SHOWN_ISSUES
    assert "... and 3 more" in output
