"""The download script: licence first, one directory per snapshot, nothing overwritten."""

import hashlib
import io
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import BinaryIO

import pytest

import fetch_mcd

TODAY = datetime(2026, 11, 6, 9, 30, tzinfo=UTC)
PAYLOAD = b"PK made-up package bytes"


def fake_opener(url: str) -> BinaryIO:
    assert url == fetch_mcd.DATASETS["ncd"]
    return io.BytesIO(PAYLOAD)


def test_fetch_writes_the_package_and_a_manifest(tmp_path: Path) -> None:
    target = fetch_mcd.fetch("ncd", tmp_path, TODAY, opener=fake_opener)
    assert target == tmp_path / "ncd-2026-11-06" / "ncd.zip"
    assert target.read_bytes() == PAYLOAD
    manifest = json.loads((target.parent / "manifest.json").read_text(encoding="utf-8"))
    assert manifest == {
        "dataset": "ncd",
        "url": fetch_mcd.DATASETS["ncd"],
        "file": "ncd.zip",
        "bytes": len(PAYLOAD),
        "sha256": hashlib.sha256(PAYLOAD).hexdigest(),
        "fetched_at": TODAY.isoformat(),
        "licence_accepted_via": fetch_mcd.LICENCE_PAGE,
    }


def test_a_second_fetch_on_the_same_day_replaces_nothing(tmp_path: Path) -> None:
    target = fetch_mcd.fetch("ncd", tmp_path, TODAY, opener=fake_opener)
    with pytest.raises(FileExistsError):
        fetch_mcd.fetch("ncd", tmp_path, TODAY, opener=lambda _: io.BytesIO(b"different"))
    assert target.read_bytes() == PAYLOAD


def test_urls_outside_the_cms_downloads_host_are_refused() -> None:
    with pytest.raises(ValueError, match="refusing to fetch"):
        fetch_mcd.open_url("file:///etc/passwd")


def test_main_refuses_to_download_without_the_licence_flag(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert fetch_mcd.main(["ncd"], raw_root=tmp_path) == 2
    assert "--accept-licence" in capsys.readouterr().out
    assert list(tmp_path.iterdir()) == []


def test_main_downloads_once_the_licence_is_accepted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(fetch_mcd, "open_url", fake_opener)
    assert fetch_mcd.main(["ncd", "--accept-licence"], raw_root=tmp_path) == 0
    assert "downloaded" in capsys.readouterr().out
    assert fetch_mcd.main(["ncd", "--accept-licence"], raw_root=tmp_path) == 1
