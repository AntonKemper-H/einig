# Einig

A mobile-first web app that helps groups decide what to do. Everyone rates the options on three levels, and the app picks the option everyone can live with rather than the one most people like.

Team project for *Introduction to Programming*, Nova SBE 2026/27.

**Deployed URL:** https://nod-lqeq.onrender.com (free plan: the first visit after a quiet period can take up to a minute)

## Objectives

- **Find a decision everyone can live with,** not just what the majority wants. One strong "Rather not" weighs more than a lukewarm "yes", so the app avoids options that someone really dislikes.
- **Make deciding quick on a phone.** No account and no app install: open the link, pick a nickname, swipe through the options.
- **Bring in real places.** Options come from Google Maps with photos, ratings, prices and a map, so the group decides on facts, not on guesses.
- **Keep it fair and private.** Votes are anonymous. Ideas can stay secret until the voting starts, and every person has one joker to rule out an option they cannot accept.

## Features

- **Create a room** in a few taps: choose what you want to do (e.g. restaurant, bar, cinema), give it a name (optional), and choose how the options are found:
  - **Own ideas:** everyone adds places by searching Google Maps by name; each match shows a small map.
  - **Popular nearby:** the creator searches around their location with radius, minimum rating, maximum price and how many places (5, 10 or up to 15).
  - **Surprise us:** a varied mix of five places from random sub-categories; anyone can swap a place they already know ("Been there").
- **Invite** with a link or a QR code. Friends join with a nickname, without an account.
- **Room setup:** limit the places each person may add and keep ideas secret until voting.
- **Lobby:** who has joined and who is done. The creator starts the voting, with an optional time limit (15, 30 or 60 minutes).
- **Rating, one card at a time:** swipe right for *Rather yes*, up for *Fine with me*, left for *Rather not*, and down for the **joker** (rules an option out, once per room). A tap turns the card to show more about the place, photos and reviews. Without JavaScript the same choices are plain buttons.
- **Result:** the winner by points (*Rather yes* +2, *Fine with me* +1, *Rather not* −4; ties: fewer "no", then more "yes"), with a map and a route link, shown with anonymous counts per option. Share it in WhatsApp or add it to your calendar.
- **Groups:** keep the same friends together and plan one activity after another.
- **My rooms:** every device sees the rooms it joined; a room can be removed from the list, and the creator can delete it for everyone.
- **If Google Maps is unavailable,** the group can add options as text for 10 minutes, so a room never gets stuck (D23).

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
   integration, region **Frankfurt** – the same as the database, and Render cannot move a service
   later.
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
