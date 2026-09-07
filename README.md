# TAWI Backend

Backend service for **TAWI 2.0** — an AI-powered app that suppresses background noise, sharpens
confusable phonemes, and transcribes speech in real time (Kenyan-accented English and Swahili),
built for people with Auditory Processing Disorder and anyone who struggles to isolate speech.

This repository is independent. It shares no code and no git history with the mobile apps
(`TAWI-Android`, `TAWI-IOS`); they coordinate only through this service's HTTP API contract.

**Current state: Phase 1 skeleton.** A FastAPI app with a `GET /health` endpoint, a Docker image,
and CI. Accounts, roles, and the AI pipeline arrive in later phases.

## Stack

| Concern               | Choice                                                          |
|-----------------------|-----------------------------------------------------------------|
| Language              | Python 3.12+                                                    |
| Framework             | FastAPI (ASGI, served by uvicorn)                               |
| Packaging / lock file | [uv](https://docs.astral.sh/uv/) — `pyproject.toml` + `uv.lock` |
| Lint & format         | ruff                                                            |
| Tests                 | pytest (via `fastapi.testclient`)                               |
| Container             | `python:3.12-slim`, non-root user                               |

## Prerequisites

- [uv](https://docs.astral.sh/uv/getting-started/installation/) — the only required tool. It
  installs the correct Python version itself, so a system Python is not needed.
- Docker (optional, only for the container workflow).

```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh
```

## Run it locally

From a fresh clone, with no other manual steps:

```bash
uv sync --all-groups                                   # create .venv from uv.lock
uv run uvicorn app.main:app --reload --port 8000       # start the API
```

Then:

```bash
curl http://127.0.0.1:8000/health
# {"status":"ok","service":"tawi-backend","version":"0.1.0","environment":"local"}
```

- Interactive API docs: <http://127.0.0.1:8000/docs>
- OpenAPI schema: <http://127.0.0.1:8000/openapi.json>

## Configuration

All settings are optional and have working defaults, so the app runs with no configuration at all.
To override, copy the template and edit it:

```bash
cp .env.example .env
```

| Variable           | Default  | Purpose                                                               |
|--------------------|----------|-----------------------------------------------------------------------|
| `TAWI_ENVIRONMENT` | `local`  | One of `local`, `ci`, `staging`, `production`. Reported by `/health`. |
| `TAWI_HOST`        | `0.0.0.0`| Bind address.                                                         |
| `TAWI_PORT`        | `8000`   | Bind port.                                                            |
| `TAWI_LOG_LEVEL`   | `info`   | uvicorn log level.                                                    |

Never commit a real `.env` — it is git-ignored. `.env.example` is the only committed template.

## Tests and lint

```bash
uv run pytest -q            # test suite
uv run ruff check .         # lint
uv run ruff format .        # auto-format
```

## Docker

```bash
docker build -t tawi-backend .
docker run --rm -p 8000:8000 tawi-backend
curl http://127.0.0.1:8000/health
```

The image installs only locked runtime dependencies (`uv sync --locked --no-dev`), runs as an
unprivileged user, and declares a `HEALTHCHECK` against `/health`.

## API

| Method | Path      | Description                                                           |
|--------|-----------|-----------------------------------------------------------------------|
| `GET`  | `/health` | Liveness probe. `200` with `{status, service, version, environment}`. |

## Continuous integration

`.github/workflows/ci.yml` runs on every push and pull request, in two independent jobs:

1. **Lint and test** — `uv sync --locked --all-groups`, `ruff check`, `ruff format --check`,
   `pytest`.
2. **Docker** — builds the image, starts the container, and asserts `/health` answers `200`.

CI installs everything from `uv.lock`, so a green run means a clean clone works with the commands
in this README and nothing else.

## Layout

```text
app/
  __init__.py     # package version
  config.py       # environment-backed settings
  main.py         # FastAPI app factory and /health
tests/
  test_health.py  # Phase 1 item 1.7 coverage
Dockerfile
pyproject.toml    # dependencies and tool config
uv.lock           # pinned, committed dependency lock file
.env.example
```

## Project docs

The PRD (`TAWI-Redesign-PRD.md`) and the phased plan (`TAWI-Development-Phases.md`) live in the
local parent working folder alongside the three repos. They are deliberately not committed here.
