# Project plan

How we get from the skeleton to the submission on **2026-11-23, 23:59**.
Scope and reasons: `docs/decisions.md`. Feature details: `docs/concept.md`.

Last updated: 2026-11-16. Tick boxes as work is merged into `main`.

---

## 1. Outside the code (this week)

- [x] Review and merge the skeleton PR (`feature-0-project-skeleton`) – a teammate, not the author
- [x] Email the teaching staff: is Flask instead of Streamlit OK? → approved
- [x] mkim-nova sets up Google Cloud: Places API (New) + Maps Embed API, two restricted keys, **budget alert (~€1)**, keys entered in Render (16 Nov). The daily quota cannot be set during the free trial; see `docs/decisions.md`, D6
- [x] **Decide together:** how are unrated options counted? → as "Fine with me" (`docs/decisions.md`, D11)
- [ ] Names and student numbers in `README.md`
- [x] Assign the three tracks below to people (`docs/decisions.md`, D10)

## 2. Three parallel tracks

Each line is one task: own spec in `specs/`, own branch, own pull request, fresh Claude Code session.

### Track A – Rooms & participants (owns the database schema) – AntonKemper-H

- [x] A1 Database schema: rooms, participants, options, votes, vetoes (`docs/concept.md` §7) (PR #5)
- [x] A2 F1 Create a room (PR #8)
- [x] A3 F2 Join without an account (PR #9)
- [x] A4 F3 Add options manually (PR #14)
- [x] A5 F7 Lobby with room status (meta refresh), including the creator's "Start voting" (collecting → voting) (PR #15)
- [x] A6 F22 QR code for the invite link, scanned on a phone on the deployed app (PR #16)
- [x] A7 F24 Delete an option (author or creator; new table `option_authors`, `docs/decisions.md` D14) (PR #38, checked on the deployed app)
- [x] A8 F25 My rooms on the home page, cookie kept 180 days (`specs/a8-my-rooms.md`, D15) (PR #46, checked on the deployed app and on a phone)
- [ ] A9 F16 Fixed groups: plan one activity after another, one-tap join (`specs/a9-groups.md`, D15) – after A8
- [ ] A10 F4 Swipe to rate + menu link on the rating card (`specs/a10-swipe-rating.md`, D16) – after C2c
- [ ] A11 F28 Hidden collecting (`specs/a11-hidden-collecting.md`, D17) – after C9 and B6

### Track B – Voting & result – Timonhio

- [x] B1 F5 Winner algorithm in `services/scoring.py` – pure functions (PR #6)
- [x] B2 F4 Three-level rating (PR #11)
- [x] B3 F6 Result page (PR #19)
- [ ] B4 F10 Joker / veto
- [ ] B5 F11 Deadline
- [ ] B6 Room page layout: participants and options collapsible, invite at the end (`specs/b6-room-page-layout.md`, D17) – after B4, B5 and C9
- [ ] B7 F29 Share and save the result: WhatsApp link and calendar file (`docs/decisions.md` D18)

### Track C – Online & places – mkim-nova

- [x] C1 Deployment on Render + hosted Postgres (`DATABASE_URL`, review of PR #1 point 3) – live at https://nod-lqeq.onrender.com with Neon (PR #7)
  - [x] C1b Invite link with https behind Render's proxy (`TRUST_PROXY_HEADERS`, PR #21)
  - [x] C1c Several requests at once: gunicorn with 2 workers × 4 threads (PR #22)
- [x] C2 F8 Places from Google (built and tested with fake responses first, real key later)
  - [x] C2a Search and save places as options (PR #12)
  - [x] C2b Cards with name, photo, rating, price, distance + photo proxy (PR #18)
- [x] C3 F9 Map and route to the winner (PR #24) – map needs `GOOGLE_MAPS_EMBED_KEY` (Google Cloud setup above)
- [x] C4 F12 Surprise mode (PR #27)
- [x] C5 F13 "Been there" (PR #29) – checked on the deployed app with a real key
- [x] C6 F23 Find a place by name and pick the right match (`docs/decisions.md` D14) (PR #39) – checked on the deployed app with a real key
- [ ] C7 F26 "I was there", "My places" and badges (`specs/c7-collect-places.md`, D15) – after A9; Track A reviews the new table
- [ ] C8 F26 Map of my places and of a group, Maps Static API (`specs/c8-place-map.md`, D15) – after C7; enable the Maps Static API for the server key first
- [ ] C9 F27 Room setup: activity, kind, options per person (`specs/c9-room-setup.md`, D17) – after C6

### Dependencies

```
A1 schema ──► A2 F1 ──► A3 F2 ──► A4 F3 ──► A5 F7
                 │          │
                 │          └──► B2 F4 ──► B3 F6 ──► B4 F10, B5 F11
                 └──► C2 F8 ──► C3 F9, C4 F12 ──► C5 F13
B1 F5 (no dependencies)        C1 deploy (no dependencies)
A8 F25 ──► A9 F16 ──► C7 F26 ──► C8 F26 map
```

## 3. Milestones

| By | Milestone |
|---|---|
| **12 Nov** | Skeleton merged · app **online** · schema merged · algorithm done |
| **16 Nov** | **Minimum version F1–F7 online** – from here we always have a submittable app |
| **20 Nov** | F8–F13, F22, F23, F24; A8 F25 |
| **21 Nov** | A9 F16, C7 + C8 F26 (D15) – cut from the end if time runs short |
| **21–22 Nov** | Click through every workflow with invalid input, fix bugs, README, rehearse the demo |
| **23 Nov** | Submit only, nothing new |

Parked until everything above works: F14–F21.

## 4. How we work

- Before every task: `git switch main && git pull`, then a new branch named after the task.
- Tests first (red), then build until green. Paste the final test output in the PR.
- Small PRs, merged within 1–2 days. No long-lived branches.
- **Review in a circle:** A reviews B, B reviews C, C reviews A. Everyone learns another part of the code for the walkthrough.
- Shared files have one owner: schema → Track A, deployment/config → Track C, `AGENTS.md` → whoever is decided; changes via PR.
- After each merge: everyone pulls `main`.
