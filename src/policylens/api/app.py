"""Build the ASGI application.

A factory rather than a module-level app, so tests and the server each get a fresh
instance, and so configuration read at startup is read once, in one place.

Run it with:
    uv run uvicorn policylens.api.app:create_app --factory
"""

from __future__ import annotations

from typing import Literal

from fastapi import FastAPI
from pydantic import BaseModel

import policylens


class Health(BaseModel):
    """What the liveness probe reports.

    Attributes:
        status: Always "ok" when the process can answer at all. Readiness that depends on
            the data snapshot will be reported separately once a snapshot exists.
        version: The running package version, so an operator can tell which release
            answered.
    """

    status: Literal["ok"]
    version: str


def healthz() -> Health:
    """Liveness: the process is up and serving requests."""
    return Health(status="ok", version=policylens.__version__)


def create_app() -> FastAPI:
    """Create the application with every route registered."""
    app = FastAPI(
        title="policylens",
        version=policylens.__version__,
        summary="Cited answers about Medicare coverage policy.",
    )
    app.add_api_route("/healthz", healthz, methods=["GET"], tags=["operations"])
    return app
