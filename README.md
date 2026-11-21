# Einig

A mobile-first web app that helps groups decide what to do. Everyone rates the options on three levels, and the app picks the option everyone can live with rather than the one most people like.

Team project for *Introduction to Programming*, Nova SBE 2026/27.

**Deployed URL:** https://nod-lqeq.onrender.com (free plan: the first visit after a quiet period can take up to a minute)

## Team

| Name | Student number |
|---|---|
| Christopher Harren | 73313 |
| Mika Samuel Kimmel | 73431 |
| Timo Nolte | 74581 |

## Run locally

Requires [uv](https://docs.astral.sh/uv/).

```bash
uv sync
cp .env.example .env               # then fill in the values (ask the team privately)
uv run flask --app app init-db
uv run flask --app app run --debug
```

## Run the tests

```bash
uv run pytest
```

## Where the data is stored

- **Locally and in tests:** SQLite (`instance/einig.sqlite`, tests use a temporary file). Leave `DATABASE_URL` empty in `.env`.
- **Deployed:** hosted Postgres (Neon), because Render deletes local files on every restart. The app switches automatically when the secret `DATABASE_URL` is set. All SQL lives in `app/db.py` and is written once, in SQLite style; `db.py` translates it for Postgres.

## Deploy on Render

Our service was created **by hand** in Render's dashboard (**New → Web Service**), not from the
Blueprint. That matters: a hand-created service does not read [`render.yaml`](render.yaml) at all.
The file is kept as the reference for the build and start commands, and every change to it has to
be copied into the dashboard by hand – see step 5.

1. Create a free Postgres database on [Neon](https://neon.tech) and copy its connection string (`postgresql://…`).
2. On [Render](https://render.com): **New → Web Service**, connect this repository through the GitHub
   integration (the repository is private, so a public URL will not do), region **Frankfurt** – the
   same as the database, and Render cannot move a service later.
3. Paste the build and start commands from [`render.yaml`](render.yaml) into the service's fields.
4. Set the environment variables under **Environment**: `DATABASE_URL` (the Neon string),
   `GOOGLE_MAPS_API_KEY`, `GOOGLE_MAPS_EMBED_KEY`, `TRUST_PROXY_HEADERS=true` (Render is exactly one
   proxy in front of the app, so the invite link and the QR code use `https://`), and a random
   `SECRET_KEY`. Never put these values in the repository.
5. **After changing `render.yaml`, update the dashboard too.** The start command there is what runs;
   the file is only documentation for this service. The same goes for new environment variables.
6. Render builds with `uv sync --frozen --no-dev`, runs `init-db` (which only creates missing tables,
   so a new table reaches the database on the next deploy without a migration) and starts `gunicorn`.
7. **Deploys:** auto-deploy is set to **On Commit**, so a merge into `main` should go live by itself
   after a few minutes. If it does not – it did not on 2026-11-16 – check **Events** for a failed
   build and use **Manual Deploy → Deploy latest commit**. Deploying a single commit or rolling back
   from the dashboard switches auto-deploy off, so check the setting after doing either.
8. Check: `https://<app>.onrender.com/health` answers `ok`. The free plan sleeps when idle – open the
   URL a minute before a demo.

## Documentation

- [`docs/concept.md`](docs/concept.md) – feature concept
- [`docs/decisions.md`](docs/decisions.md) – team decisions, scope and timeline
- [`docs/course-briefing.md`](docs/course-briefing.md) – course requirements and grading
- [`AGENTS.md`](AGENTS.md) – rules for coding agents
- [`specs/`](specs/) – one spec per task
