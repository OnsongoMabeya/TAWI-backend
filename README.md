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

## Roadmap

Only the work owned by **this** repo is listed. Item numbers refer to `TAWI-Development-Phases.md`.
Each phase is a separate commit here, prefixed with its phase number, and a phase is not done until
its exit gate is met.

- [x] **Phase 1 — Repo scaffolding & CI baseline** (1.2, 1.5–1.7, 1.10)
      FastAPI skeleton, `GET /health`, Dockerfile, lock file, CI, this README.

- [ ] **Phase 2 — Accounts & roles** *(backend-only phase; the mobile repos are untouched)*
  - 2.2 User model: id, role, linked accounts (child ↔ parent, child ↔ therapist), email/password
    auth with refresh tokens
  - 2.3 Consent fields: COPPA/GDPR-style consent timestamp, data retention preference
  - 2.4 Role-based access middleware enforcing the PRD's permission matrix
  - 2.5 CRUD: account creation, login, link Caregiver to child, link Therapist to adult user
  - 2.6–2.8 Tests: password hashing, token issue/refresh, role checks (positive **and** negative),
    linked-caregiver integration flow, rejection of expired/invalid tokens on every protected route
  - *Exit gate 2.9: the permission matrix is enforced **and** covered by automated tests*

- [ ] **Phase 3 — AI pipeline (server-side MVP)** *(backend-only phase)*
  - 3.2 Whisper-based speech-to-text for English and Swahili
  - 3.3 Noise suppression as an audio pre-processing step
  - 3.4 Decide and **document** the phoneme-enhancement approach (spectral emphasis vs.
    model-based correction) before building it, then implement server-side
  - 3.5 `POST /process-audio` → `{ transcript, enhanced_audio_url, confidence }`
  - 3.6–3.8 Tests: WER benchmark on Kenyan-accented English/Swahili (tracked, not pass/fail),
    latency budget, output stability across repeated runs
  - *Exit gate 3.9: WER baseline documented; endpoint stable under repeated calls*

- [ ] **Phase 4 — Mobile foundations**
      No build work here, but this repo is a dependency: both apps need a reachable
      `/process-audio` (local or staging URL) plus Phase 2 auth to complete their round trip (4.1, 4.4).

- [ ] **Phase 5 — Real-time mode**
  - 5.2 Move audio transport to streaming (WebSocket or gRPC streaming) with chunked inference so
    partial transcripts return incrementally
  - 5.6 End-to-end latency target (~1s) measured across all three repos — isolate the culprit
    before fixing, since a failure can originate in any of them

- [ ] **Phase 6 — Offline / on-device mode**
  - 6.5 Sync/reconciliation endpoint for queued offline sessions to upload once connectivity returns

- [ ] **Phase 7 — Accessibility & consent hardening**
  - 7.6 Account/data deletion endpoint; retention policy enforced server-side
  - 7.10 Tests: a minor account cannot be created without guardian consent captured server-side;
    a deletion request actually removes data (verified in the database, not just the UI)

- [ ] **Phase 8 — Caregiver/therapist dashboards & sharing**
  - 8.4 Report generation endpoint; sharing-permission model with access scope and expiry
  - 8.6 Test: a shared link exposes only what was explicitly shared, and expires/revokes correctly

- [ ] **Phase 9 — Async mode & dialect expansion**
  - 9.2 Async (non-streaming) processing for the review flow
  - 9.4 Dialect coverage beyond English/Swahili, per a language-priority list
  - 9.7 Test: each new dialect meets the Phase 3 WER bar before it ships

- [ ] **Phase 10 — Monetization & entitlements**
  - 10.2 Entitlement service defining which features are Pro-gated
  - 10.5 Test: a free-tier account cannot reach Pro-gated endpoints **via direct API calls** —
    never trust the client

- [ ] **Phase 11 — Beta hardening & launch readiness**
  - 11.2 Full end-to-end regression pass with the mobile repos
  - 11.4 Privacy-respecting crash reporting and analytics, consistent with Phase 7 consent settings
  - 11.6 Regression suite green independently here
  - 11.8 Pilot dry run (5–10 users) with no data loss

## Project docs

The PRD (`TAWI-Redesign-PRD.md`) and the phased plan (`TAWI-Development-Phases.md`) live in the
local parent working folder alongside the three repos. They are deliberately not committed here.
