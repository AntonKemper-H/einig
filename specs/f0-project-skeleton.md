# F0 – Project skeleton

Branch: `feature-0-project-skeleton`
Tests: `tests/test_skeleton.py`

## Why
Every later feature needs a running Flask app, a database connection and a test setup with a temporary database. This task creates that empty but working base in the structure from `AGENTS.md`, so the three team members can start on features in parallel.

## What
- [ ] `uv sync` installs pinned dependencies from `pyproject.toml` + `uv.lock`: `flask`, `python-dotenv`, `gunicorn` (production server for Render); dev only: `pytest`.
- [ ] `create_app()` in `app/__init__.py` builds the app. With a test config it uses that config instead of environment variables.
- [ ] Rejected: the app refuses to start without a `SECRET_KEY` and raises an error that names the missing variable. No hard-coded fallback key.
- [ ] `GET /` shows a home page with the app name "Einig" (status 200).
- [ ] The home page is mobile-first: it contains the viewport meta tag.
- [ ] The home page loads Pico.css from our own `static/` folder, not from an external URL (privacy rule: no external resources).
- [ ] `GET /health` returns status 200 and the text `ok` (for the hosting health check).
- [ ] Edge case: an unknown URL returns status 404 with a friendly "Page not found" page, not a crash.
- [ ] `uv run flask --app app init-db` creates the database and prints a confirmation.
- [ ] `init-db` never deletes data: running it on an existing database keeps all rows (review #1, point 2).
- [ ] `uv run flask --app app reset-db` deletes all data only after the user confirms with "y".
- [ ] Rejected: answering "n" to `reset-db` keeps all data unchanged.
- [ ] Python is pinned to 3.12 (`.python-version` and `requires-python = ">=3.12,<3.13"`) (review #1, point 1).
- [ ] Tests use a temporary SQLite database (fixture in `tests/conftest.py`), never a real one.

## Out of scope
- No tables for rooms, participants, options or votes (Sprint 1, F1–F3; the schema owner designs them).
- No Postgres / `DATABASE_URL` support yet (separate task C1 in `docs/plan.md`, before the real deployment; review #1, point 3).
- No Google Maps, no `requests`, no PWA files, no JavaScript.
- No deployment to Render in this branch (next step, needs an account).
- No styling beyond Pico.css defaults and a minimal `base.html`.

## Done when
- `uv run pytest` passes; final output pasted.
- `uv run flask --app app run --debug` shows the home page in the browser; an unknown URL shows the 404 page.
- Starting without `SECRET_KEY` fails with a clear message.
- Work is on branch `feature-0-project-skeleton`, pushed, pull request opened and reviewed by a teammate.
- (No "restart keeps data" check yet: there is no data to keep. It starts with F1.)
