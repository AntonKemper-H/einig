# Project plan

How we get from the skeleton to the submission on **2026-11-23, 23:59**.
Scope and reasons: `docs/decisions.md`. Feature details: `docs/concept.md`.

Last updated: 2026-11-10. Tick boxes as work is merged into `main`.

---

## 1. Outside the code (this week)

- [ ] Review and merge the skeleton PR (`feature-0-project-skeleton`) – a teammate, not the author
- [ ] Email the teaching staff: is Flask instead of Streamlit OK? (still Python, pytest, uv)
- [ ] One member sets up Google Cloud: Places API (New) + Maps Embed API, two restricted keys, **budget alert (~€1) and daily quota** – needed from about 17 Nov
- [ ] **Decide together:** how are options counted that a participant did not rate? (blocks the scoring tests, see `docs/decisions.md` → Open questions)
- [ ] Names and student numbers in `README.md`
- [ ] Assign the three tracks below to people

## 2. Three parallel tracks

Each line is one task: own spec in `specs/`, own branch, own pull request, fresh Claude Code session.

### Track A – Rooms & participants (owns the database schema)

- [ ] A1 Database schema: rooms, participants, options, votes, vetoes (`docs/concept.md` §7)
- [ ] A2 F1 Create a room
- [ ] A3 F2 Join without an account
- [ ] A4 F3 Add options manually
- [ ] A5 F7 Lobby with room status (meta refresh)
- [ ] A6 F22 QR code

### Track B – Voting & result

- [ ] B1 F5 Winner algorithm in `services/scoring.py` – pure functions, **can start immediately**
- [ ] B2 F4 Three-level rating (needs A1 + A3)
- [ ] B3 F6 Result page
- [ ] B4 F10 Joker / veto
- [ ] B5 F11 Deadline

### Track C – Online & places

- [ ] C1 Deployment on Render + hosted Postgres (`DATABASE_URL`) – **can start immediately**
- [ ] C2 F8 Places from Google (built and tested with fake responses first, real key later)
- [ ] C3 F9 Map and route to the winner
- [ ] C4 F12 Surprise mode
- [ ] C5 F13 "Been there"

### Dependencies

```
A1 schema ──► A2 F1 ──► A3 F2 ──► A4 F3 ──► A5 F7
                 │          │
                 │          └──► B2 F4 ──► B3 F6 ──► B4 F10, B5 F11
                 └──► C2 F8 ──► C3 F9, C4 F12 ──► C5 F13
B1 F5 (no dependencies)        C1 deploy (no dependencies)
```

## 3. Milestones

| By | Milestone |
|---|---|
| **12 Nov** | Skeleton merged · app **online** · schema merged · algorithm done |
| **16 Nov** | **Minimum version F1–F7 online** – from here we always have a submittable app |
| **20 Nov** | F8–F13, F22 |
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
