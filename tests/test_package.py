"""The package's own metadata agrees with itself."""

import tomllib
from pathlib import Path

import policylens

ROOT = Path(__file__).resolve().parent.parent


def test_version_matches_pyproject() -> None:
    # The health endpoint reports this string, so a release where the two disagree would
    # tell an operator the wrong thing about what is running.
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    assert policylens.__version__ == project["version"]
