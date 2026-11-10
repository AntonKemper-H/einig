# Einig

A mobile-first web app that helps groups decide what to do. Everyone rates the options on three levels, and the app picks the option everyone can live with rather than the one most people like.

Team project for *Introduction to Programming*, Nova SBE 2026/27.

**Deployed URL:** _coming soon_

## Team

| Name | Student number |
|---|---|
| _Name 1_ | _number_ |
| _Name 2_ | _number_ |
| _Name 3_ | _number_ |

## Run locally

Requires [uv](https://docs.astral.sh/uv/).

```bash
uv sync
cp .env.example .env               # then fill in the values (ask the team privately)
uv run flask --app app init-db
uv run flask --app app run --debug
```

`init-db` works once the data model task has added `app/db.py` and `schema.sql`; the skeleton
runs without it.

## Run the tests

```bash
uv run pytest
```

## Documentation

- [`docs/concept.md`](docs/concept.md) – feature concept
- [`docs/decisions.md`](docs/decisions.md) – team decisions, scope and timeline
- [`docs/course-briefing.md`](docs/course-briefing.md) – course requirements and grading
- [`AGENTS.md`](AGENTS.md) – rules for coding agents
- [`specs/`](specs/) – one spec per task
