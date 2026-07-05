# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

A FastAPI backend for an English vocabulary learning app. Users register/login (JWT auth) and manage a personal list of words with spaced-repetition-style review tracking (PostgreSQL via SQLAlchemy, Alembic migrations). Code comments throughout are in Russian.

## Commands

This is a Windows venv checked out under WSL (`venv/Scripts/...`, not `venv/bin/...`). Run Python tooling via the venv's Windows executables, or use whatever Python 3 interpreter is on PATH with the packages from `requirements.txt`/`requirements-dev.txt` installed.

- Run the API locally: `uvicorn app.main:app --reload` (also configured as the "FastAPI Debug" launch config in `.vscode/launch.json`)
- Run all tests: `pytest`
- Run a single test file: `pytest tests/unit/test_crud_words.py`
- Run a single test: `pytest tests/unit/test_auth.py::test_login_user`
- Apply DB migrations: `alembic upgrade head`
- Create a new migration after changing `app/models.py`: `alembic revision --autogenerate -m "description"`

Requires a `.env` file (not committed) with `DATABASE_URL`, `SECRET_KEY`, `ALGORITHM`, `ACCESS_TOKEN_EXPIRE_MINUTES`. Tests do not need this — they run against an in-memory SQLite DB (see below).

## Architecture

**Layering**: `routers/` (HTTP endpoints, request/response models) → `crud/` (DB queries and business logic) → `models.py` (SQLAlchemy ORM tables). `schemas.py` holds all Pydantic request/response models for both routers. `auth.py` holds JWT creation/verification and the `get_current_user` dependency; password hashing helpers (`pwd_context`) live there too and are imported by `crud/users.py`.

**Routing**: All endpoints are mounted under `/api/v1` via a prefix router in `app/main.py`, which includes `routers/auth.py` (mounted at `/api/v1/auth`) and `routers/words.py` (mounted at `/api/v1/words`). Legacy top-level routes (`/login`, `/register`, `/me`) 307-redirect to their `/api/v1/...` equivalents for backward compatibility.

**Route ordering matters**: in `routers/words.py`, the static routes `/random` and `/stats` must stay declared *before* the parametrized `/{word_id}` route, or FastAPI will match them as a `word_id` path param instead.

**Auth flow**: `POST /api/v1/auth/login` uses `OAuth2PasswordRequestForm` (form-encoded `username`/`password`, not JSON) and returns a JWT with `sub` = user email. Protected endpoints depend on `auth.get_current_user`, which decodes the token, re-fetches the user from the DB by email, and 401s if the token is invalid or the user no longer exists.

**Ownership scoping**: every word query in `crud/words.py` filters by both `word_id` and `owner_id` together, so users can never read/modify/delete another user's words — preserve this double-filter pattern when adding new word endpoints.

**Review/learning logic**: `crud/words.py::review_word` increments `Word.review_count` and auto-sets `is_learned = True` once `review_count >= LEARNED_THRESHOLD` (currently 5). `toggle_learned` is the separate manual override path (`PATCH /{word_id}/learned`) and does not touch `review_count`.

**Error responses**: a global `RequestValidationError` handler and `HTTPException` handler in `app/exceptions.py` wrap all errors into a consistent `{"error": {"code": ..., "message": ...}}` shape (validation errors additionally include a `details` list from Pydantic). Tests assert against this envelope, not FastAPI's default error format.

**Pagination**: `GET /api/v1/words` returns `PaginatedWordResponse` (`items`, `total`, `page`, `size`, `pages`). `page` is computed as `skip // limit`, i.e. it's a derived offset-based page index, not necessarily equal to "requests since start" if `skip` isn't a clean multiple of `limit`.

## Testing

- `tests/conftest.py` overrides the `get_db` dependency with a shared in-memory SQLite engine (via `StaticPool` so all connections see the same DB) and provides `client`, `db_session`, `test_user`, and `test_word` fixtures.
- `tests/unit/` tests CRUD functions directly; `tests/integration/test_api.py` drives full request/response flows through the `TestClient`.
- The `test_user` fixture's password hash corresponds to plaintext `"secret"` — use that when logging in through the API in a test rather than the CRUD layer.
