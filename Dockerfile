# The production image. Two stages: the first resolves the locked environment with uv, the
# second carries only that environment, so the build tools and the source tree never ship.

FROM python:3.12-slim AS build

COPY --from=ghcr.io/astral-sh/uv:0.13.6 /uv /usr/local/bin/uv

# Compile bytecode at build time so the first request isn't paying for it, copy rather than
# hard-link out of the cache (the cache isn't in the final image), and never download an
# interpreter: the base image's Python is the one we tested.
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# Dependencies first, in their own layer, so a code-only change rebuilds in seconds.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --locked --no-dev --no-install-project

COPY src ./src
RUN uv sync --locked --no-dev --no-editable


FROM python:3.12-slim

# A fixed, unprivileged user. Nothing in this service needs root, so nothing gets it.
RUN useradd --create-home --uid 10001 app

WORKDIR /app
COPY --from=build /app/.venv /app/.venv

# Hosts such as Render tell the service which port to bind through $PORT.
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8000

USER app
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import os, urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.environ[\"PORT\"]}/healthz', timeout=3)"]

# exec so uvicorn is PID 1 and receives the host's SIGTERM directly for a clean shutdown.
CMD ["sh", "-c", "exec uvicorn policylens.api.app:create_app --factory --host 0.0.0.0 --port \"$PORT\" --no-server-header"]
