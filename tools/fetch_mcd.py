"""Download a Medicare Coverage Database package into the local raw cache.

CMS publishes the packages behind a click-through licence (AMA for CPT, ADA for CDT, AHA for
UB-04). Downloading one accepts those terms, so this script won't run without
`--accept-licence`, which a person passes on purpose after reading them at LICENCE_PAGE.

Each download lands in its own new directory, `data/raw/<dataset>-<YYYY-MM-DD>/`, beside a
`manifest.json` recording the URL, size, SHA-256 and time. Nothing under `data/raw/` is ever
committed. An existing download is never overwritten: a snapshot is evidence, and replacing
it would change what an earlier build meant.

Usage:
    uv run python tools/fetch_mcd.py ncd --accept-licence
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.request
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import BinaryIO

ROOT = Path(__file__).resolve().parent.parent

#: Where a person reads the licence terms before passing --accept-licence.
LICENCE_PAGE = "https://www.cms.gov/medicare-coverage-database/downloads/downloads.aspx"

_EXPORTS = "https://downloads.cms.gov/medicare-coverage-database/downloads/exports/"

#: The packages this project reads, by short name.
DATASETS: dict[str, str] = {
    "ncd": _EXPORTS + "ncd.zip",
    "current-lcd": _EXPORTS + "current_lcd.zip",
    "current-article": _EXPORTS + "current_article.zip",
}

#: Opens a URL and returns a readable byte stream. Injected so tests never touch the network.
Opener = Callable[[str], BinaryIO]

_CHUNK = 1024 * 1024


def open_url(url: str) -> BinaryIO:
    """Open a CMS URL with a timeout, identifying the client honestly.

    Raises:
        ValueError: If the URL isn't an https URL on the CMS downloads host. Every URL comes
            from `DATASETS`, so this guards against an edit, not against input.
    """
    if not url.startswith(_EXPORTS):
        raise ValueError(f"refusing to fetch outside {_EXPORTS}: {url}")
    request = urllib.request.Request(url, headers={"User-Agent": "policylens-fetch"})
    return urllib.request.urlopen(request, timeout=120)


def fetch(dataset: str, raw_root: Path, today: datetime, opener: Opener = open_url) -> Path:
    """Download one package and write its manifest.

    Args:
        dataset: A key of `DATASETS`.
        raw_root: The raw cache directory, normally `data/raw`.
        today: When the download happens; names the directory and goes in the manifest.
        opener: How to open the URL.

    Returns:
        The path of the downloaded package.

    Raises:
        FileExistsError: If this dataset was already downloaded today.
    """
    url = DATASETS[dataset]
    directory = raw_root / f"{dataset}-{today.date().isoformat()}"
    directory.mkdir(parents=True, exist_ok=False)
    target = directory / url.rsplit("/", 1)[1]

    digest = hashlib.sha256()
    size = 0
    with opener(url) as response, target.open("wb") as file:
        while chunk := response.read(_CHUNK):
            digest.update(chunk)
            size += len(chunk)
            file.write(chunk)

    manifest = {
        "dataset": dataset,
        "url": url,
        "file": target.name,
        "bytes": size,
        "sha256": digest.hexdigest(),
        "fetched_at": today.isoformat(),
        "licence_accepted_via": LICENCE_PAGE,
    }
    (directory / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    return target


def main(argv: Sequence[str] | None = None, raw_root: Path = ROOT / "data" / "raw") -> int:
    """Parse arguments and download. Returns 0 on success, 2 if the licence wasn't accepted."""
    parser = argparse.ArgumentParser(description="Download a CMS coverage package.")
    parser.add_argument("dataset", choices=sorted(DATASETS))
    parser.add_argument(
        "--accept-licence",
        action="store_true",
        help=f"confirm you have read and accept the licence terms at {LICENCE_PAGE}",
    )
    args = parser.parse_args(argv)
    if not args.accept_licence:
        print(f"Downloading accepts the AMA, ADA and AHA licence terms at {LICENCE_PAGE}.")
        print("Read them, then rerun with --accept-licence.")
        return 2
    try:
        target = fetch(args.dataset, raw_root, datetime.now(UTC), opener=open_url)
    except FileExistsError:
        print(f"{args.dataset} was already downloaded today; nothing replaced.")
        return 1
    print(f"downloaded {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
