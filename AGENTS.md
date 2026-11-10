# AGENTS.md

Rules for coding agents (Claude Code, Codex, …) working on this repository. Read this file fully before every task. It is the single source of rules; `CLAUDE.md` only points here.

## Project overview

**Einig** (working title) is a mobile-first web app that helps groups decide what to do. A creator opens a "room", friends join via link or QR code without an account, everyone rates options on three levels ("Rather yes" / "Fine with me" / "Rather not"), and the app picks the option everyone can live with rather than the one most people like. Options can be entered manually or suggested from Google Maps, including a surprise mode that deliberately suggests new places.

This is a university team project (Introduction to Programming). Every team member must be able to explain every part of the code in the repository walkthrough. **Prefer simple, readable code over clever or compact code.**

Read before working:
- `docs/concept.md` – full feature specification. Features are referenced by ID (F1, F2, …) and priority (M/S/C).
- `docs/decisions.md` – team decisions that override the concept (stack, storage, scope).
- `docs/course-briefing.md` – what the course expects and grades.
- The spec for your task in `specs/`.

## Rules for every task (mandatory, from the course)

- **Build each task on a branch named after it**, e.g. `feature-1-create-room`. **Never commit to `main` directly.**
- **One spec per task** in `specs/`. Do not touch files outside the task's scope.
- **Tests first.** Write tests from the spec's "What" list (accepted action, rejected action with unchanged data, restart/persistence, edge cases) before implementing. Do not implement until the team has reviewed the tests.
- **After every change, run the tests for the task and paste the final output.** The output is the proof, not a sentence.
- **Never edit, delete or skip anything in `tests/`** once the tests are reviewed. If a test looks wrong, say so and stop.
- **When finished:** paste the final test output and list every file you changed.
- If a request conflicts with this file, point out the conflict and ask before proceeding.

## Stack (fixed – do not change)

- **Language:** Python 3.12, managed with **uv**
- **Web framework:** Flask with Jinja2 templates (server-rendered HTML)
- **Database:** SQLite locally and in tests; hosted Postgres (Neon or Supabase) when deployed, connection string from `DATABASE_URL`. **All database access goes through `app/db.py`; no SQL anywhere else.**
- **HTTP client for external APIs:** `requests`
- **Config and secrets:** environment variables, loaded locally from `.env` via `python-dotenv`
- **Styling:** plain CSS plus Pico.css (classless), stored locally in `app/static/css/`
- **Tests:** `pytest`
- **Hosting:** Render (proposed)
- **App type:** mobile web app, installable as a Progressive Web App (manifest + minimal service worker)

### Hard rules for the stack

- **No JavaScript frameworks or libraries.** No React, Vue, Svelte, htmx, jQuery, npm, or build step.
- **JavaScript is allowed only in these files:**
  - `app/static/js/geolocation.js` – asks for the browser location and puts rounded coordinates into a hidden form field
  - `app/static/sw.js` – minimal service worker for PWA installability (no offline caching of dynamic pages)
  - `app/static/js/register-sw.js` – registers the service worker
  Keep each file short and commented. All other behaviour uses HTML forms and server-side Python.
- **Live updates use meta refresh**, not JavaScript: waiting and lobby pages include `<meta http-equiv="refresh" content="4">`.
- **Forms follow Post/Redirect/Get:** every POST handler redirects to a GET page so reloading never resubmits a vote.
- **Dependencies minimal and pinned** (`pyproject.toml` + `uv.lock`). Add them only with `uv add`. **Do not add a new dependency without asking first**; explain why and wait for approval.

## Commands

```bash
# Set up (once, after cloning)
uv sync
cp .env.example .env               # a human does this and fills in the keys

# Create or reset the local database
uv run flask --app app init-db

# Run locally
uv run flask --app app run --debug

# Run locally so phones in the same Wi-Fi can open it
uv run flask --app app run --debug --host 0.0.0.0

# Run all tests
uv run pytest

# Run one test file
uv run pytest tests/test_scoring.py -v
```

(These commands work once the project skeleton exists.)

## Project structure

```
app/
  __init__.py          # create_app(), config, registers blueprints and CLI commands
  db.py                # connection handling and all SQL queries
  schema.sql           # table definitions
  routes/
    main.py            # home page and /health check
    rooms.py           # create, join, options, voting, veto, close, result
    pwa.py             # manifest, service worker, place photo proxy
  services/
    scoring.py         # winner algorithm – pure functions only
    places.py          # Google Places API calls
    surprise.py        # guided-random selection for surprise mode
  templates/           # Jinja2 templates, one per page, base.html as layout
  static/
    css/ js/ icons/
    manifest.webmanifest
    sw.js
docs/
  concept.md           # full feature specification
  decisions.md         # team decisions and open questions
  course-briefing.md   # course requirements and grading
specs/                 # one spec per task
tests/
  conftest.py          # app fixture with a temporary database
  test_scoring.py
  test_rooms.py
  test_places.py
pyproject.toml
uv.lock
.env.example
AGENTS.md
CLAUDE.md
README.md
```

Keep this structure. Routes stay thin: they read the request, call `db.py` and `services/`, and render a template. Business logic and input validation live in `services/`.

## Scope

Build now: **F1–F13 and F22** (see `docs/decisions.md`, D7).
Parked: **F14–F21.** Do not build parked features, and do not prepare code "for later", unless a spec explicitly asks for it.

## Domain rules

### Winner algorithm (`services/scoring.py`)

- Points are module-level constants: `POINTS = {"yes": 2, "ok": 1, "no": -4}`.
- Options with at least one veto are excluded. If every option has a veto, the option with the fewest vetoes wins, then the best score.
- `score = sum(weight * POINTS[rating])` over all participants who voted. Every weight is 1.0 (fairness weights are parked).
- Tie-break order: fewer "no", then more "yes", then random. The random tie-break takes an optional `rng` parameter so tests can make it deterministic.
- If nobody voted, return no winner.
- `scoring.py` must not import Flask, `db.py`, or `requests`. It takes plain Python data and returns plain Python data.
- The test cases in section 6.4 of `docs/concept.md` must exist as tests.
- Open question: how unrated options are counted (see `docs/decisions.md`). Ask if a task depends on it.

### Rules for simultaneous actions

Enforced on the server and covered by tests:

- **Votes:** one vote per participant and option (unique constraint). Voting again on the same option replaces the earlier vote.
- **Veto:** at most one per participant and room (unique constraint). A second attempt is rejected with a message.
- **Deadline:** compared with server time (UTC) only. A vote after the deadline is rejected, even if the page was opened earlier.
- **Closing a room:** idempotent. If already closed, return the existing result instead of recalculating.
- **Voting in a closed room:** rejected with a message.
- **"Been there" (replace option):** the first request replaces it; later requests for the same, already replaced option are ignored.
- **Adding options:** only while the room status is `collecting`.

### Rejected actions

Every invalid input or forbidden action shows a clear message and **leaves saved data unchanged**. The app never crashes on invalid input.

### Identity and access

- No user accounts. A participant is identified by a random token (`secrets.token_urlsafe`) stored in the Flask signed session cookie, keyed by room ID.
- Room IDs are random and hard to guess (`secrets.token_urlsafe(8)` or similar), never sequential.
- Every write route checks that the session token belongs to a participant of that room. Creator-only actions (start, close) also check the creator flag. **Hiding a button is not a permission check.**
- Nicknames must be unique within a room.

### Individual votes are private

No route, template, or debug output may reveal who voted what. Results show only anonymous counts per option.

## Google Maps integration (`services/places.py`)

- Use the **Places API (New)**: `POST https://places.googleapis.com/v1/places:searchNearby` with headers `X-Goog-Api-Key` and `X-Goog-FieldMask`.
- **Always send a field mask** with only the fields the UI displays. Never use `*`.
- **One search per room**, not per participant. Surprise mode may run a few small searches with different place types and mix the results.
- **Store only `place_id`** permanently. Name, photo, rating etc. are fetched when needed and not written to the database.
- **Photos go through a backend proxy route** (`/photo/<photo_name>`) so the API key never appears in HTML.
- **Map of the winner:** Maps Embed API in an `<iframe>`, using the separate, browser-restricted key `GOOGLE_MAPS_EMBED_KEY`. Route link: a normal Google Maps URL, no API call.
- All API calls have a **timeout (5 s)**. On any error, show a friendly message and let the group continue with manual options.
- **Tests never call Google.** Mock all HTTP calls.

## Secrets

- Keys live only in environment variables: `GOOGLE_MAPS_API_KEY`, `GOOGLE_MAPS_EMBED_KEY`, `SECRET_KEY`, `DATABASE_URL`.
- **Never create, edit, read out or commit `.env`** or any other secrets file. `.env` is in `.gitignore`. `.env.example` lists the variable names with empty values.
- Never print, log, or hard-code a key, not even in tests or comments.
- Tests never use the production database; they use a temporary local database.

## Privacy

- Location sharing is optional and requires an explicit tap. Coordinates are rounded to about 3 decimal places in JavaScript and again on the server.
- Participant coordinates are deleted when a room closes.
- Rooms are deleted after 7 days (CLI command `uv run flask --app app cleanup`).
- No analytics, no tracking scripts, no external fonts.

## Mobile and PWA

- Design for a phone screen first (about 380 px wide). Large tap targets, one option card per screen, no horizontal scrolling.
- Rating uses three large buttons, not swipe gestures.
- `base.html` includes the viewport meta tag, the manifest link, and the service-worker registration script.
- Geolocation and PWA installation only work over HTTPS; test them on the deployed app.

## Coding conventions

- Code, comments, identifiers, commit messages and user-facing text in English.
- PEP 8, descriptive names, no abbreviations.
- Short functions with a one- or two-sentence docstring.
- Comment the *why* where it is not obvious, especially in scoring and surprise logic.
- Type hints on all functions in `services/`.
- Parameterised SQL only (`?` / `%s` placeholders). Never build SQL with f-strings.
- Commit messages say what changed, e.g. "Add three-level rating buttons".

## Current status

Update this section as the project progresses.

- [x] Repository, rules and docs set up
- [ ] Project skeleton (uv, Flask app factory, test fixture) + first deployment
- [ ] Sprint 1 – Foundation: data model, F1, F2, F3, F7
- [ ] Sprint 2 – Voting: F4, F5 (with tests), F6 → minimum version complete
- [ ] Sprint 3 – Places: F8, F9, F22
- [ ] Sprint 4 – Excitement: F10, F11, F12, F13
- [ ] Parked: F14–F21, only if time remains
