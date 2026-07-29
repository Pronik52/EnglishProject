# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

A FastAPI app for learning English vocabulary in context, plus a small vanilla-JS SPA served from the same origin. Users register/login (JWT in an HttpOnly cookie for the browser, Bearer for API clients) and build a personal word list. Each word gets an AI-generated example phrase and a generated "scene" picture; words are drilled with spaced repetition. Code comments throughout are in Russian.

The distinguishing mechanic is the **describe mode**: the app generated the picture, so it knows the ground truth (`Word.scene_prompt`) and can grade a free-form English description with a cheap *text* LLM instead of a multimodal one. `scene_prompt` is deliberately never sent to the client — it is the answer key.

Main pieces beyond CRUD: a curated word catalog by CEFR level and topic (`routers/catalog.py`), server-built study sessions (`routers/study.py`), image generation (`image_generator.py`), phrase generation (`ai_generator.py` with an offline fallback in `phrases.py`), and answer grading (`evaluator.py`). All four external integrations never raise — they log and fall back.

## Commands

This is a Windows venv checked out under WSL (`venv/Scripts/...`, not `venv/bin/...`). Run Python tooling via the venv's Windows executables, or use whatever Python 3 interpreter is on PATH with the packages from `requirements.txt`/`requirements-dev.txt` installed.

- Run the API locally: `uvicorn app.main:app --reload` (also configured as the "FastAPI Debug" launch config in `.vscode/launch.json`)
- Run all tests: `pytest`
- Run a single test file: `pytest tests/unit/test_crud_words.py`
- Run a single test: `pytest tests/unit/test_auth.py::test_login_user`
- Apply DB migrations: `alembic upgrade head`
- Create a new migration after changing `app/models.py`: `alembic revision --autogenerate -m "description"`

- Seed the catalog: `python -m app.seed_catalog` (idempotent, reads `data/catalog_seed.json`)

Requires a `.env` file (not committed) with `DATABASE_URL`, `SECRET_KEY`, `ALGORITHM`, `ACCESS_TOKEN_EXPIRE_MINUTES`; see `.env.example` for the optional image/LLM/limit settings. Tests do not need this — they run against an in-memory SQLite DB (see below).

Note the local interpreter is Python 3.9, so new modules using `str | None` annotations need `from __future__ import annotations`.

## Architecture

**Layering**: `routers/` (HTTP endpoints, request/response models) → `crud/` (DB queries and business logic) → `models.py` (SQLAlchemy ORM tables). `schemas.py` holds all Pydantic request/response models. `auth.py` holds JWT creation/verification and the `get_current_user` dependency; password hashing helpers (`pwd_context`) live there too and are imported by `crud/users.py`. There is no settings module — config is read ad-hoc via `os.getenv`.

**Routing**: All endpoints are mounted under `/api/v1` via a prefix router in `app/main.py`, which includes `routers/auth.py` (`/api/v1/auth`), `routers/words.py` (`/api/v1/words`), `routers/catalog.py`, `routers/billing.py`, and `routers/study.py`. Legacy top-level routes (`/login`, `/register`, `/me`) 307-redirect to their `/api/v1/...` equivalents. The SPA is served as static files at `/app`, generated pictures at `/media`.

**Route ordering matters**: in `routers/words.py`, the static routes `/random`, `/stats`, `/preview-phrase` must stay declared *before* the parametrized `/{word_id}` route, or FastAPI will match them as a `word_id` path param instead.

**Auth flow**: `POST /api/v1/auth/login` sets an HttpOnly `access_token` cookie plus a JS-readable `csrf_token`; `POST /api/v1/auth/token` returns a Bearer JWT for Swagger and API clients. Both use `OAuth2PasswordRequestForm` (form-encoded `username`/`password`, not JSON) with `sub` = user email. A CSRF middleware in `main.py` checks cookie == `X-CSRF-Token` header == the `csrf` claim inside the JWT on unsafe methods, but only when a cookie session is present — Bearer clients bypass it naturally. Both cookies are set with `path=/`, not `/api/v1`: the browser only exposes a cookie to `document.cookie` when its path matches the *page* URL, and the SPA lives at `/app`. Scoping them to the API prefix left the frontend unable to read `csrf_token`, so every unsafe request was rejected while GETs kept working. `logout` deletes both paths because old `/api/v1` cookies are not overwritten by the new ones.

**Ownership scoping**: every word query in `crud/words.py` filters by both `word_id` and `owner_id` together, so users can never read/modify/delete another user's words — preserve this double-filter pattern when adding new word endpoints.

**SRS**: `crud/words.py::_apply_srs` is the single place progress changes. Correct → `srs_level + 1` (capped at `SRS_MAX_LEVEL = 5`), wrong → back to 0; `due_at = now + SRS_INTERVALS_DAYS[level]`; `is_learned` is derived from `srs_level >= 5`. Every answer also appends a `ReviewLog` row via `_log_review`, uncommitted so it lands atomically with the word change. `toggle_learned` is the manual override path.

**"Due" is one rule, defined once**: `crud/words.py::due_filter` — not learned, and `due_at` is null or past. Both the dashboard counter (`get_words_stats`) and the study session (`crud/study.py`) use it. Do not re-inline the condition; when it was written twice, the number promised on the dashboard could disagree with what training actually offered.

**Study sessions are built server-side** (`crud/study.py::build_session`), so the web client and a future iOS client share one implementation. The server picks the words *and* the mode per card, following a difficulty ladder keyed on `srs_level`: 0–1 → `choice` (recognise among 4 options), 2–3 → `type` (recall and write), ≥4 → `describe` (use it in your own sentence). `describe` degrades to `type` when the word has no picture; `choice` degrades to `type` when fewer than 3 distractors can be gathered. Distractors are collected **once per session** (own words first, topped up from `catalog_words`) — never per card. `options` are returned for every card that can have them, not only `choice` ones, so the client's manual mode override stays usable.

**Limits are anti-abuse, not a tariff** (`DAILY_WORD_LIMIT`, `DAILY_DESCRIBE_LIMIT`, `REGEN_LIMIT` in `crud/words.py`, all env-overridable). Payment was removed from the UI because it was a demo that never charged anything while its limits blocked the first session. The `is_premium` model is intentionally kept in the DB for when real payments arrive; the demo `POST /billing/activate` is gated behind `BILLING_DEMO_ENABLED` because without the flag it hands out Premium to any authenticated caller.

**The client holds no copies of server constants.** `GET /words/stats` returns `srs_max_level`, `regen_limit` and `words_left_today` alongside the counts; `frontend/js/dictionary.js` reads them via `setRules`. Duplicated constants used to sit in the frontend and drifted silently.

**Error responses**: a global `RequestValidationError` handler and `HTTPException` handler in `app/exceptions.py` wrap all errors into a consistent `{"error": {"code": ..., "message": ...}}` shape (validation errors additionally include a `details` list from Pydantic). Tests assert against this envelope, not FastAPI's default error format.

**Pagination**: `GET /api/v1/words` returns `PaginatedWordResponse` (`items`, `total`, `page`, `size`, `pages`). `page` is computed as `skip // limit`, i.e. it's a derived offset-based page index, not necessarily equal to "requests since start" if `skip` isn't a clean multiple of `limit`.

## Frontend (`frontend/`)

A single `index.html` with view sections toggled by a `.hidden` class, no build step and no framework. ES modules in `frontend/js/`:

- `core.js` — the `api()` fetch wrapper (adds the CSRF header, handles 401), plus shared helpers and Web Speech TTS. It imports nothing on purpose: the other modules import each other in a ring, and only a fully independent core guarantees `$`/`api` exist by the time their code runs.
- `app.js` — entry point. `refresh()` reloads counts + word list; `refreshStats()` updates only the counts. Per-word actions redraw their own card from the server's response instead of calling `refresh()`.
- `onboarding.js` — first-run wizard (level → topic → starter set), shown when the dictionary is empty. It ends by starting a session, not by returning to the dashboard.
- `study.js` — renders whatever `GET /study/session` returns. Mode selection, ordering and distractors all live on the server; the header `<select>` defaults to "auto" and is only a manual override.
- `dictionary.js` — word list and catalog.

## Testing

- `tests/conftest.py` overrides the `get_db` dependency with a shared in-memory SQLite engine (via `StaticPool` so all connections see the same DB) and provides `client`, `db_session`, `test_user`, and `test_word` fixtures.
- `tests/unit/` tests CRUD functions directly; `tests/integration/test_api.py` drives full request/response flows through the `TestClient`.
- The `test_user` fixture's password hash corresponds to plaintext `"secret"` — use that when logging in through the API in a test rather than the CRUD layer.
- An autouse `offline_mode` fixture forces `GROQ_API_KEY=""` and `IMAGE_PROVIDER=off`, so tests exercise the offline fallbacks and never hit the network.

## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

Rules:
- For codebase questions, first run `graphify query "<question>"` when graphify-out/graph.json exists. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).
