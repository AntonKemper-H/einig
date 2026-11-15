# Team decisions

Decisions the team has made so far, with the reason for each. When a decision changes, update this file and `AGENTS.md` in the same pull request.

Last updated: 2026-11-12

---

## Project facts

- Course: Introduction to Programming, Nova SBE 2026/27 (full requirements: `docs/course-briefing.md`)
- Team: 3 members, all with GitHub accounts. Task split: see D10.
- **Deadline: repo link on Moodle by 2026-11-23, 23:59.** Commits after that are ignored.
- Presentation: 24 Nov or 04 Dec (live demo at the public URL + repository walkthrough)
- Grading: works 20% · UI/UX 20% · scope 20% · tests 10% · security 10% · walkthrough 20%

## D1 – We build a new app: "Einig"

A group decision app (full concept: `docs/concept.md`). We do not extend a solo project.

## D2 – Stack: Flask + Jinja2 templates + Pico.css, not Streamlit

- **Why:** we want a better-looking, mobile-first interface than Streamlit offers. Flask with server-rendered HTML is still Python, is listed on the course site as an alternative ("FastAPI/Flask + HTML"), and lets us check permissions on the server where each action happens.
- **Not chosen:** Streamlit (weak UI control, reruns on every click), NiceGUI (middle ground), React/JS frontend (needs staff approval, two languages, two deployments; too much for 3 weeks).
- **Approved** by the teaching staff (2026-11-12): Flask instead of Streamlit is fine.

## D3 – Tooling follows the course: uv + pytest

- `uv` manages Python and dependencies; versions pinned in `pyproject.toml` + `uv.lock` (security criterion).
- Not `pip` + `requirements.txt` (the concept's original suggestion).

## D4 – Storage: SQLite locally and in tests, hosted Postgres when deployed

- **Why:** free hosts (Render, Streamlit Cloud) have a temporary disk, so a SQLite file is deleted on every restart. In a live multi-user app that would wipe all rooms mid-demo, and the course requires accepted changes to survive a restart.
- **Plan:** hosted Postgres (Neon or Supabase, free). Connection string from the secret `DATABASE_URL`. All DB code stays in `app/db.py`. Tests keep using a temporary local database.
- **Status:** to be set up before the first real deployment. Free hosted DBs may pause when idle; wake it before the presentation.

## D5 – Hosting: Render (proposed)

Streamlit Community Cloud only hosts Streamlit apps. Render (free) runs Flask. Deploy early (target: 2026-11-12) so problems show up early.

## D6 – Places data: Google Maps, not OpenStreetMap

- **Why:** photos, ratings and price levels make the cards much better. OpenStreetMap would be free and keyless but has none of these.
- **Needs:** one team member creates a Google Cloud account with a payment method, enables Places API (New) and Maps Embed API, and creates two keys:
  - `GOOGLE_MAPS_API_KEY` – server only, restricted to Places API
  - `GOOGLE_MAPS_EMBED_KEY` – browser, restricted to our domain
- **Cost protection (mandatory):** budget alert at about €1 and a daily quota for the Places API (e.g. 200 requests/day).
- **Key handling:** only in local `.env` and the host's secret settings. Shared privately between members. Never in the repo, in code, or in a chat with an AI. If leaked: delete the key in Google Cloud Console immediately and create a new one.
- Tests never call Google (fake responses). Members without a key can still work and test.
- If Google fails: friendly message, group continues with manual options.

## D7 – Scope

Concept priorities M/S/C apply, with this cut for the submission:

| Build now | Parked (only after the core works and is deployed) |
|---|---|
| F1–F7 minimum version | F14 Blind Date |
| F8–F11 places, map, joker, deadline | F15 Fate mode |
| F12–F13 surprise mode, "been there" | F16–F18 groups, history, fairness memory |
| F22 QR code | F19 meeting point, F20 travel times, F21 WebSockets |

**Why:** Claude Code writes code fast, but reviews, understanding every part for the walkthrough, browser testing and merges take time. A smaller app that never crashes scores better than a big one that does.

## D8 – Rough timeline

| Dates | Goal |
|---|---|
| 10–12 Nov | Repo, rules, project skeleton, "hello world" deployed |
| 13–16 Nov | Minimum version F1–F7 live |
| 17–20 Nov | F8–F13, F22 |
| 21–22 Nov | Bug fixes, invalid input, README, rehearse demo |
| 23 Nov | Submit only, nothing new |

## D9 – Team workflow (from the course)

1. `git switch main && git pull`, then a new branch named after the task.
2. One spec per task in `specs/`, one fresh Claude Code session per task.
3. Tests first (red), then build until green.
4. Commit, push, open a pull request.
5. **Another member reviews**; the author never merges their own PR unreviewed.
6. Merge, everyone pulls `main`.

Split work **by feature**. Shared files (database schema, `app/__init__.py`, `AGENTS.md`) have one owner each, decided when tasks are assigned.

## D10 – Task split (2026-11-12)

| Track | Owner (GitHub) | Also owns |
|---|---|---|
| A – Rooms & participants | AntonKemper-H | Database schema (`app/schema.sql`) |
| B – Voting & result | Timonhio | `app/services/scoring.py` |
| C – Online & places | mkim-nova | Deployment, hosting config, Google Cloud account and keys |

Reviews go in a circle: A reviews B, B reviews C, C reviews A.

## D11 – Unrated options count as "Fine with me" (2026-11-12)

- A participant who rated **at least one** option counts as a voter. For every option this voter did **not** rate, the algorithm uses "ok" (+1).
- A participant who rated **no** option is not counted at all (matches F11: non-voters are not counted). If nobody rated anything, there is no winner.
- **Why:** silence means "I can live with it". This way every voter contributes to every option, so all options are compared on equal terms.
  Example, 3 voters: A is rated only by P1 ("yes"), B is rated "ok" by all three. With the rule: A = 2 + 1 + 1 = 4, B = 1 + 1 + 1 = 3, so A wins – the same result as if P2 and P3 had pressed "Fine with me" on A.
- Vetoes are unaffected: a missing rating is never a veto.

## D12 – The "more yes" tie-break stays (2026-11-14)

- The tie-break order stays as in `AGENTS.md` and `docs/concept.md` §6.2: fewer "no", then more "yes", then random.
- **Why:** with D11 and every weight at 1, the "more yes" step can never decide on its own: for n voters an option's score is `n + yes − 5 × no`, so equal score and equal "no" always means equal "yes" (see the note in `specs/b1-scoring.md`). It costs one element in the sort key, and it decides again as soon as fairness weights (F14–F21, parked) give voters different weights. Dropping it would mean changing `AGENTS.md`, the concept and the code for no gain today.
- Raised in the B1 review (PR #6); Anton and Mika both saw no reason to drop it.

## Open questions

- Final app name.
- Final point values after test runs.
