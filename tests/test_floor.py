"""The floor scan catches each way of quietly lowering the bar, and nothing else.

The forbidden patterns are assembled from pieces here, so this file doesn't trip the scan
it is testing.
"""

from pathlib import Path

import pytest

import floor

NOQA = "# no" + "qa"
TYPE_IGNORE = "# type" + ": ignore"
NO_COVER = "# pragma" + ": no cover"
SKIP = "@pytest.mark." + "skip"
STUB = "raise NotImplemented" + "Error"


def rules(path: str, text: str) -> list[str]:
    return [finding.rule for finding in floor.scan_text(path, text)]


@pytest.mark.parametrize("comment", [NOQA, NOQA + ": E501", TYPE_IGNORE, NO_COVER])
def test_suppression_comments_are_refused(comment: str) -> None:
    assert rules("src/policylens/x.py", f"value = 1  {comment}\n") == ["suppression"]


def test_suppressions_only_count_in_python() -> None:
    # Prose may discuss these comments; only code can use them.
    assert rules("README.md", f"Never write `{NOQA}`.\n") == []


def test_a_skip_without_a_reason_is_refused() -> None:
    assert rules("tests/test_x.py", f"{SKIP}\ndef test_x() -> None: ...\n") == ["skip"]


def test_a_skip_with_a_reason_is_allowed() -> None:
    text = f'{SKIP}if(True, reason="needs the CMS download")\n'
    assert rules("tests/test_x.py", text) == []


def test_a_stub_is_refused_in_the_package() -> None:
    assert rules("src/policylens/x.py", f"def f() -> None:\n    {STUB}\n") == ["stub"]


def test_a_stub_outside_the_package_is_not_a_finding() -> None:
    # Tests may legitimately assert that something raises it.
    assert rules("tests/test_x.py", f"def f() -> None:\n    {STUB}\n") == []


def test_an_except_that_only_passes_is_refused() -> None:
    text = "try:\n    f()\nexcept ValueError:\n    # nothing to do\n\n    pass\n"
    assert rules("src/policylens/x.py", text) == ["swallow"]


def test_an_except_that_handles_the_error_is_allowed() -> None:
    text = "try:\n    f()\nexcept ValueError:\n    pass_count += 1\n    log()\n"
    assert rules("src/policylens/x.py", text) == []


def test_an_except_whose_block_ends_before_a_pass_elsewhere_is_allowed() -> None:
    text = "try:\n    f()\nexcept ValueError:\n    raise\npass\n"
    assert rules("src/policylens/x.py", text) == []


@pytest.mark.parametrize(
    "secret",
    [
        "AKIA" + "ABCDEFGHIJKLMNOP",
        "ghp_" + "a" * 36,
        "github" + "_pat_" + "a" * 40,
        "sk-" + "ant-" + "a" * 30,
        "sk-" + "a" * 40,
        "-----BEGIN " + "PRIVATE KEY-----",
    ],
)
def test_credentials_are_refused_in_any_text_file(secret: str) -> None:
    assert rules("config.yml", f"token: {secret}\n") == ["secret"]


def test_findings_carry_the_line_number_and_text() -> None:
    (finding,) = floor.scan_text("src/policylens/x.py", f"a = 1\nb = 2  {NOQA}\n")
    assert (finding.line, finding.text) == (2, f"b = 2  {NOQA}")


def test_scan_files_skips_binaries_and_missing_files(tmp_path: Path) -> None:
    (tmp_path / "bad.py").write_text(f"x = 1  {NOQA}\n", encoding="utf-8")
    (tmp_path / "image.png").write_bytes(b"\x89PNG " + NOQA.encode())
    (tmp_path / "blob.py").write_bytes(b"\xff\xfe\x00")
    found = floor.scan_files(["bad.py", "image.png", "blob.py", "gone.py"], root=tmp_path)
    assert [(f.path, f.rule) for f in found] == [("bad.py", "suppression")]


def test_the_repository_itself_is_clean() -> None:
    # The scan has to pass on this repository, or `check` could never go green.
    assert floor.scan_files(floor.committable_files()) == []


def test_main_reports_and_fails_on_a_finding(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "bad.py").write_text(f"x = 1  {NOQA}\n", encoding="utf-8")
    assert floor.main(["bad.py"], root=tmp_path) == 1
    assert "bad.py:1: suppression" in capsys.readouterr().out


def test_main_passes_on_a_clean_repository(capsys: pytest.CaptureFixture[str]) -> None:
    assert floor.main() == 0
    assert "clean" in capsys.readouterr().out
