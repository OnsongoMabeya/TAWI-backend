# TAWI Backend

Backend service for **TAWI 2.0** — an AI-powered app that suppresses background noise, sharpens
confusable phonemes, and transcribes speech in real time (Kenyan-accented English and Swahili),
built for people with Auditory Processing Disorder and anyone who struggles to isolate speech.

This repository is independent. It shares no code and no git history with the mobile apps
(`TAWI-Android`, `TAWI-IOS`); they coordinate only through this service's HTTP API contract.

**Current state: Phase 2.** Accounts with roles and permission rules are live (register, login,
refresh-rotation, caregiver/therapist pairing codes, session-list access control), on PostgreSQL
with Alembic migrations. The AI audio pipeline arrives in Phase 3.

## Stack

| Concern               | Choice                                                                   |
|-----------------------|--------------------------------------------------------------------------|
| Language              | Python 3.12+                                                             |
| Framework             | FastAPI (ASGI, served by uvicorn)                                        |
| Packaging / lock file | [uv](https://docs.astral.sh/uv/) — `pyproject.toml` + `uv.lock`          |
| Lint & format         | ruff                                                                     |
| Tests                 | pytest (via `fastapi.testclient`)                                        |
| Container             | `python:3.12-slim`, non-root user                                        |
| Database              | PostgreSQL 17 (dev via `docker compose`), SQLAlchemy 2.0 async + Alembic |

## Prerequisites

- [uv](https://docs.astral.sh/uv/getting-started/installation/) — it installs the correct Python
  version itself, so a system Python is not needed.
- Docker (required since Phase 2: the dev and test databases are real Postgres in containers).

```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh
```

## Run it locally

From a fresh clone:

```bash
uv sync --all-groups                                   # create .venv from uv.lock
docker compose up -d db                                # dev Postgres on 127.0.0.1:5433
uv run alembic upgrade head                            # apply the schema
uv run uvicorn app.main:app --reload --port 8000       # start the API
```

The dev database URL default in the app matches `docker-compose.yml`, so no configuration is
needed. The API still answers `/health` without the database — but account endpoints require it.

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

| Variable                           | Default                                              | Purpose                                                                                                                       |
|------------------------------------|------------------------------------------------------|-------------------------------------------------------------------------------------------------------------------------------|
| `TAWI_ENVIRONMENT`                 | `local`                                              | `local`/`ci`/`staging`/`production`. Reported by `/health`.                                                                   |
| `TAWI_HOST` / `TAWI_PORT`          | `0.0.0.0` / `8000`                                   | Bind address and port.                                                                                                        |
| `TAWI_LOG_LEVEL`                   | `info`                                               | uvicorn log level.                                                                                                            |
| `TAWI_DATABASE_URL`                | `postgresql+asyncpg://tawi:tawi@127.0.0.1:5433/tawi` | Postgres DSN; the default matches `docker-compose.yml`.                                                                       |
| `TAWI_JWT_SECRET`                  | dev-only placeholder                                 | Access-token signing key. **Required outside local/ci** — the app refuses to boot with the placeholder in staging/production. |
| `TAWI_ACCESS_TOKEN_TTL_SECONDS`    | `900` (15 min)                                       | Access-token lifetime.                                                                                                        |
| `TAWI_REFRESH_TOKEN_TTL_SECONDS`   | `2592000` (30 d)                                     | Refresh-token lifetime.                                                                                                       |
| `TAWI_PAIRING_CODE_TTL_SECONDS`    | `900` (15 min)                                       | Caregiver/therapist pairing-code lifetime.                                                                                    |

Never commit a real `.env` — it is git-ignored. `.env.example` is the only committed template.

## Tests and lint

The suite always runs against a real PostgreSQL: the session fixture creates/reset the `tawi_test`
database and runs the real migrations (`alembic upgrade head`) from scratch on every run, so a
green suite means the migration chain is clean and reversible from zero.

```bash
docker compose up -d db     # once — the test DB is created automatically in the same container
uv run pytest -q            # test suite
uv run ruff check .         # lint
uv run ruff format .        # auto-format
```

Override the test database location with `TAWI_TEST_DATABASE_URL` if you run Postgres elsewhere.

## Docker

```bash
docker build -t tawi-backend .
docker run --rm -p 8000:8000 tawi-backend
curl http://127.0.0.1:8000/health
```

The image installs only locked runtime dependencies (`uv sync --locked --no-dev`), runs as an
unprivileged user, and declares a `HEALTHCHECK` against `/health`.

## API

| Method | Path                   | Description                                                                                                |
|--------|------------------------|------------------------------------------------------------------------------------------------------------|
| `GET`  | `/health`              | Liveness probe. `200` with `{status, service, version, environment}`.                                      |
| `POST` | `/auth/register`       | Create an account (role, DOB, consent). `201` → tokens + profile.                                          |
| `POST` | `/auth/login`          | `200` → tokens + profile. Unknown email and wrong password are indistinguishable (both 401).               |
| `POST` | `/auth/refresh`        | Rotating refresh: new access **and** refresh token; reuse of a rotated token revokes the family.           |
| `POST` | `/auth/logout`         | Revokes the presented refresh token. `204`.                                                                |
| `GET`  | `/users/me`            | Own profile.                                                                                               |
| `POST` | `/users/me/link-codes` | Listener mints a one-time pairing code (`grants: caregiver \| therapist`), 15-minute expiry.               |
| `POST` | `/links/redeem`        | Caregiver/therapist redeems a code; permission rules enforced again server-side.                           |
| `GET`  | `/users/{id}/sessions` | A listener's session list, guarded by the permission matrix. Unauthorised requesters get **404**, not 403. |

The permission rules themselves live in `app/permissions.py` as pure functions — the full matrix is
unit-tested (positive and negative) in `tests/test_permissions.py`; the same matrix is exercised
end-to-end in `tests/test_linking_and_sessions.py`.

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
  __init__.py          # package version
  config.py            # environment-backed settings
  db.py                # engine lifecycle (created in the app lifespan)
  deps.py              # current-user + permission dependencies
  permissions.py       # pure role-permission matrix (unit-tested directly)
  schemas.py           # request/response models
  models/account.py    # users, user_links, link_codes, refresh_tokens
  models/session.py    # sessions, session_transcripts, session_audio (phase 3+)
  security/passwords.py  # argon2id hashing + strength rules
  security/tokens.py     # access JWTs + rotating refresh tokens
  routers/auth.py        # register / login / refresh / logout
  routers/users.py       # me, pairing codes, redeem, session lists
alembic/               # migration environment and versions
tests/                 # unit, permission-matrix and integration suites
Dockerfile
docker-compose.yml     # dev/test Postgres only, not the app
pyproject.toml
uv.lock
.env.example
```

## Roadmap

Only the work owned by **this** repo is listed. Item numbers refer to `TAWI-Development-Phases.md`.
Each phase is a separate commit here, prefixed with its phase number, and a phase is not done until
its exit gate is met.

- [x] **Phase 1 — Repo scaffolding & CI baseline** (1.2, 1.5–1.7, 1.10)
      FastAPI skeleton, `GET /health`, Dockerfile, lock file, CI, this README.

- [x] **Phase 2 — Accounts & roles** *(backend-only phase; the mobile repos are untouched)*
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
local parent working folder
