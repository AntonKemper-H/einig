# Course briefing for the coding agent — Introduction to Programming (Nova SBE, 2026/27)

> Source: the course wiki at https://2477-introduction-programming.gitlab.io/wiki/ (all pages read on 2026-11-10).
> Purpose: tell the coding agent (Claude Code) everything the course expects, so it works the way the course grades.
> Claude Code reads `CLAUDE.md`. The course standard is `AGENTS.md`. Put the rules in `AGENTS.md` and let `CLAUDE.md` say: "Read and follow AGENTS.md."

---

## 0. Where we are right now

- Today: **2026-11-10 = Class 9, Block 3 (Team project, weeks 8–10).**
- **Team project repo link due on Moodle: 2026-11-23, 23:59** (one member submits). Commits after the deadline are ignored.
- Presentations: **24 Nov (1/2)** and **04 Dec (2/2)**, half of the teams each week.
- Exam: 2026-12-19, 17:30 (make-up 2027-01-13, 16:00). 30 multiple-choice questions about the agentic workflow (planning a task, briefing an agent, judging the result). No code reading.
- Grading: team project 40%, exam 60%. All team members get the same project grade.

---

## 1. What the team project must be

- Team of 3–4. Either **extend one member's solo project** (Plot Twist / Campus Tycoon / Festival Architect, see §7) or **build a new app** of the team's choice. Open scope, judged against what 3–4 people can do in 3 weeks.
- Must be **deployed at a public URL**. The live demo runs there (no slides or videos instead).
- Possible directions (examples, not requirements): multiple users / accounts / shared live data; external public APIs; reports & exports (charts, CSV, PDF); roles (e.g. manager approves employee's submission); notifications (email/reminders); new workflows the solo project did not have.
- Every member must contribute code to the repository.

### Repository requirements (submission)
- **Public** GitHub repository.
- **No keys or passwords** in it (see §5 Secrets).
- `main` branch contains the code of the deployed app.
- `README.md` with: **deployed URL**, **names and student numbers of all members**, **commands to run the app and the tests locally**.

### Presentation
1. **Live demo** at the deployed URL.
2. **Repository walkthrough**: staff opens the repo and asks high-level questions; any member can be asked about any part. Example questions: *Where is the data stored? What do the tests cover, and what not? What happens if the external API is unavailable?*

### Grading criteria (Low 30% / Mid 70% / High 100%)
| # | Criterion | Weight | What "High" means |
|---|---|---|---|
| 1 | It works | 20% | Deployed app runs **all workflows without errors, including invalid input**. |
| 2 | UI & UX | 20% | Interface fits the problem; workflows are direct; **results and errors are clearly shown**. |
| 3 | Scope & ambition | 20% | Substantial features well beyond a solo project, implemented consistently. |
| 4 | Verification | 10% | Tests cover **accepted and rejected actions and edge cases**, and **all pass on main**. |
| 5 | Security | 10% | Access control and input validation enforced; **dependencies minimal, pinned, no known vulnerabilities**; no credentials in repo. |
| 6 | Repository walkthrough | 20% | Members explain how it is built, **why**, its **limits**, and how it could change. |

Implication for the agent: favour a plain app that works over a polished one that crashes; keep the code explainable; validate every input; write tests for rejected actions.

---

## 2. Default stack and project structure

- **Python + Streamlit + SQLite + pytest, run with `uv`.** (Leaving Python requires approval from the teaching staff — do not switch on your own.)
- Commands:
  - Run app: `uv run streamlit run app.py`
  - Run tests: `uv run pytest`
  - Reset/seed data (if present): `uv run python seed.py`
- Structure (same as course apps):
  - `app.py` — screens (entry point; one function per screen)
  - `logic.py` — rules, calculations, validation
  - `db.py` — storage; nothing else touches the data files/database
  - `tests/` — pytest tests
  - `specs/` — one spec per task (e.g. `specs/first-feature.md`)
  - `docs/` — product brief (BRD) copy, e.g. `docs/product-brief.md`
  - `data/` / `seed/` — live data and pristine seed copy (if used)
  - `AGENTS.md`, `README.md`
- Keep local database files and secrets out of git.

---

## 3. The agentic standards the course teaches (follow these)

### 3.1 Rulebook — `AGENTS.md`
Only what the agent cannot work out from the code: commands, boundaries, repo etiquette, how to report. Short. It lives in git and changes via pull requests. When the agent misbehaves, the fix is usually one new line here.

Three mandatory rules (from Class 4):
- Build each task on a **branch named after it** (e.g. `feature-2-categories`). **Never commit to main directly.**
- After every change, **run the tests for the task and paste the final output**. The output is the proof, not a sentence.
- **Never edit, delete or skip anything in `tests/`.** If a test looks wrong, say so and stop.

Plus, from the setup page / guides:
- Never create or edit `.env` or other secret files; secrets are read from environment variables / `.streamlit/secrets.toml`, never hard-coded; secrets files are in `.gitignore`.
- One issue or spec per task. Don't touch `data/` by hand.
- When done: paste the test output and **list every file changed**.

### 3.2 Spec — one per task, four sections
- **Why** — intent (2 sentences), used to pick the safe reading of ambiguous lines.
- **What** — checklist `- [ ]`, one line per thing that must be true; one line = one test. Reference BRD requirement/rule IDs.
- **Out of scope** — the fence; name what the agent will be tempted to do.
- **Done when** — finish line in plain words (tests green, visible in app, on branch, pushed). Must include: an accepted action, a **rejected action with unchanged data**, and a **restart that restores accepted changes**.

### 3.3 Judge — define done before building
- **Tests first**, from the What checklist, before implementation. Review them against the brief; then keep them fixed. Correct a wrong test explicitly against the BRD; never weaken it to get green.
- Run tests **red first** — the failing tests are the to-do list. Read red from the bottom.
- Green is not the end: read the diff (only what the task needed?) and click through the app. A Done-when line without a test is checked by clicking.
- Tests must not call real external APIs or real AI models (use fake responses) and must not use the real/production database (use temporary/local DB).

### 3.4 Loop — one task, a stop condition
red → edit → run tests → read failure → fix → run again → green → stop.
- One task per loop, own branch.
- The ask always has four parts: **task** (one thing), **fence** (branch + what not to touch), **finish line** (keep going until tests pass), **proof** (paste output, list files).
- Same failure twice → stop, re-read, start a fresh session with a better prompt (long contexts degrade — "context rot").
- Optional autonomous mode: `/goal every test in tests/... passes, shown by the final pytest output, and nothing in tests/ changed. Stop after 20 turns.` Only after a red test exists.

### 3.5 Team git workflow
1. Switch to main, pull. New branch named after the task.
2. Do the task in a **new session** per task.
3. Verify: run tests, paste output, run the app.
4. Commit (message says what changed, e.g. "Fix group title showing the id"), push.
5. Open pull request; **a teammate reviews** (does what was asked, tests cover it incl. rejected actions, nothing outside scope touched, especially tests). Author does not merge own PR without review.
6. Merge; everyone pulls main before the next task.
- Merge conflicts: update branch from main, resolve keeping both changes where possible, run tests, explain each conflict.
- Small, frequent merges; no long-lived branches. One owner for shared structures (data schema, `app.py`, `AGENTS.md`).
- Two agents must never edit the same folder at once.

---

## 4. Technical decision guides (summary)

Each guide's advice to the agent: describe the **decision and its reasons**, not the steps; record the decision in `AGENTS.md`.

### Stack
Streamlit suits forms, tables, charts, dashboards. Not good for drag & drop, games, animations, pixel-perfect design, or live multi-user state (it reruns the whole script per user per interaction). Alternatives: Gradio/NiceGUI/Reflex; FastAPI/Flask + HTML; JS frameworks (Next.js, SvelteKit, Vite+React — needs staff approval). Don't switch stack late, don't mix two stacks without reason, every member must understand it.

### Storing data
| Option | Survives restart | Shared by all users |
|---|---|---|
| In memory (`st.session_state`) | No | No |
| JSON/CSV files | Only if host keeps disk | One server only |
| SQLite (course default) | Only if host keeps disk | One server only |
| Hosted relational DB (Supabase, Neon, Turso) | Yes | Yes |
| Backend service (Supabase, Firebase, PocketBase) | Yes | Yes |
| Document DB (MongoDB Atlas, Firestore) | Yes | Yes |
| Key-value (Upstash Redis) | Yes | Yes |
| Google Sheets | Yes | Yes (slow, rate limits, no rules) |

- Streamlit Community Cloud has a **temporary disk** → SQLite data is lost on restart. Fine for a demo that reseeds on startup; not for real persistence. Smallest move: SQLite → hosted Postgres (both SQL).
- Example instruction: "Move storage from SQLite to hosted Postgres because the deployed app restarts and loses data. Keep all DB code in `db.py`. Read the connection string from secret `DATABASE_URL`. Keep the tests on a local database."
- Free hosted DBs may pause when idle — wake them before the presentation. Seed script keeps team data aligned. One owner for schema changes.

### Hosting
- Deploy early (week 8). Options: **Streamlit Community Cloud** (free, no card, Streamlit only, sleeps, temporary disk, public repo); Render / Railway / Hugging Face Spaces; containers (Fly.io, Cloud Run, Azure — card usually needed); Vercel/Netlify/Cloudflare (not for Streamlit); GitHub Pages (static only); student cloud credits (set spending alert).
- Ask the agent to prepare dependency/config files and how secrets are read for the chosen host, and to verify the app runs from a **fresh clone**.
- Pitfalls: uncommitted files; secrets not set in host settings; temporary disk; sleeping app at demo time (open URL beforehand); host not deploying latest `main`.

### User accounts
- Needed only if users need their own data or roles. Options: none; shared password; sign in with Google/Microsoft/GitHub (Streamlit `st.login`, Auth0); Supabase Auth / Firebase Auth; Clerk/Auth0; own password system (risky — never store plain-text passwords).
- State permissions as testable rules incl. rejected cases (e.g. "Members see only their own loans… a member who opens the returns page sees an error").
- **Hiding a button is not a permission** — check permissions where the action happens. Prepare demo accounts per role on the deployed app.

### Real-time / multiplayer
- Options: manual refresh button; polling (`st.fragment(run_every=...)`); Supabase Realtime / Firebase; WebSockets (non-Streamlit stack); Ably/Pusher/Liveblocks.
- Shared state must be in shared storage, not session memory. Define a **conflict rule** for simultaneous actions (e.g. first saved wins, second rejected with message) and test it. Test with two browsers.

### External APIs
- Free, no key: Open-Meteo (weather), Frankfurter (ECB exchange rates), REST Countries, Nager.Date (holidays), OpenStreetMap Nominatim. With key: Alpha Vantage, FMP, Mapbox, Resend/Brevo (email), Telegram/Slack/Discord webhooks.
- Required: a **failure plan** (show last saved value + message, or disable feature — never crash), timeout (e.g. 5 s), all API calls in one module, cache responses (Streamlit reruns on every click), tests use fake responses.

### AI in the app
- Needs API access (ChatGPT/Claude subscriptions don't include it). Options: OpenRouter (some free models), OpenAI/Anthropic/Google AI Studio/Mistral, Groq/Together, local Ollama/LM Studio (won't run on free hosting).
- Narrow task; **validate model output** before saving (e.g. category must be in `CATEGORIES`, else "Other"); key from env var (e.g. `OPENROUTER_API_KEY`); tests use fake responses; know what the app shows when the model is unavailable; set spending limits.

### Coding agents
Codex (used in class, reads `AGENTS.md`), **Claude Code (reads `CLAUDE.md`, which should point to `AGENTS.md`)**, Copilot, Cursor, Gemini CLI, OpenCode/Aider. Mixing agents is fine if all follow the same rules file. Read every change before accepting.

### Working as a team
Split **by feature** (best fit for agentic work); one owner for shared files; track work with GitHub issues linked to PRs (or `TODO.md`); review every PR; small merges; rules changes to `AGENTS.md` via PR.

### Secrets and safety
- Secrets: API keys, DB connection strings/passwords, login provider secrets, bot/webhook tokens. (Deployed URL, service names, example data are not secrets.)
- Local: `.env` or `.streamlit/secrets.toml` — **in `.gitignore` before creating them**. Deployed: host's secrets settings. Commit a `.env.example` with placeholders. Share real values privately.
- Code reads secrets by name (e.g. `os.environ["OPENROUTER_API_KEY"]` / `st.secrets[...]`).
- Before the first commit that uses a secret, confirm the secrets file is ignored by git.
- After a leak: revoke immediately, create new key, update local + host, check usage. Deleting the commit is not enough.
- Give keys the lowest permissions needed. Don't paste keys into chats.

---

## 5. Suggested `AGENTS.md` (adapt to the team's choices)

```markdown
# Rules
- Run the app with: uv run streamlit run app.py
- Run the tests with: uv run pytest
- Reset data with: uv run python seed.py   (if applicable)
- Structure: screens in app.py, rules in logic.py, storage in db.py, tests in tests/, specs in specs/, product brief in docs/.
- Stack: Python, Streamlit, <storage choice + why>, pytest, uv. Hosted on <host>. Do not introduce another stack.

## How to answer
- Build each task on a branch named after it, e.g. feature-2-categories. Never commit to main directly.
- One spec or issue per task. Do not touch files outside the task's scope.
- After every change, run the tests for the task and paste the final output. The output is the proof, not a sentence.
- Never edit, delete or skip anything in tests/. If a test looks wrong, say so and stop.
- Write tests first from the spec's "What" list (accepted action, rejected action with unchanged data, restart/persistence, edge cases); do not implement until they are reviewed.
- Validate all user input in logic.py; rejected actions must not change saved data and must show a clear message.
- Secrets are read from environment variables / .streamlit/secrets.toml, never written in code. Never create, edit or commit .env or secrets files.
- Tests never call real external APIs, real AI models, or the production database; use fakes and a temporary DB.
- Keep dependencies minimal and pinned.
- When finished: paste the final test output and list every file you changed.
```

And `CLAUDE.md`:
```markdown
Read and follow AGENTS.md. It is the single source of rules for this project.
```

---

## 6. Ask template (four parts)

```
Build specs/<task>.md. Work only on the branch <task-branch>.
After every change, run uv run pytest tests/<test_file>.py and keep going until every test passes.
Do not edit anything in tests/.
When they pass, paste the final test output and list every file you changed.
```

Planning ask before building:
```
Read the product brief in docs/ and specs/<task>.md.
List the state this workflow needs, what must be saved, and the rule that rejects an invalid action.
Propose tests for the allowed action, the rejected action, and restarting the app.
Do not implement yet. Point out any requirement you cannot determine from these files.
```

---

## 7. Solo project briefs (BRDs) — baseline if the team extends one

Common rules: accepted changes survive an app restart; rejected actions leave saved data unchanged; core works with supplied content, no paid service needed. Theme/name/UI may change; required behaviour is the baseline.

### 7.1 Plot Twist — 5 scenes · 2 items · 2 endings
Short (~10 min) mystery/escape room. One ending depends on an earlier choice or item. Text + simple controls.
- **PT01 Start and resume** — new game; resume if save exists; starting over asks for confirmation.
- **PT02 Explore** — show scene and available actions; every accepted choice gives a visible result.
- **PT03 Collect and use** — inventory; ≥1 item unlocks an action; no duplicates.
- **PT04 Consequences** — ≥1 remembered decision affects a later action/ending; blocked actions explained or hidden.
- **PT05 Finish and replay** — endings clearly identified; after an ending story actions stop.
- Rules: **R1** action only if scene + prerequisites satisfied; blocked action doesn't move player/change inventory. **R2** item collectable only where available, once per game; items not consumed. **R3** visited scenes reflect changes (no second key). **R4** new game resets progress, keeps story; every ending reachable.
- Remember: story content; current scene, items, decisions, ending reached. Save after each accepted action.
- Acceptance: A1 locked route rejected, state unchanged · A2 with key route opens, key kept · A3 no duplicate collection · A4 resume restores scene/item/choice after restart · A5 two different endings from new games; ending is final · A6 cancel restart keeps progress, confirm restores opening state.
- Out of scope: story editor, procedural generation, multiplayer, combat, live AI dialogue.

### 7.2 Campus Tycoon — 3 products · 5 days · €100 start
- **CT01** show day, cash, stock, progress; confirm before replacing run. **CT02** buy positive whole quantities; show total cost; reject unaffordable; update cash+stock together. **CT03** set positive selling price per product; show demand rule. **CT04** trade one day: units sold, revenue, COGS, gross profit per product and total. **CT05** history; after day 5 show final cash, remaining stock at cost, overall gain/loss; stop buying/trading.
- **R1 Demand**: price ≤ ref → 10 units; ref < price ≤ 2×ref → 5; > 2×ref → 0. No randomness. **R2** sold = min(demand, stock); unsold carries over. **R3** euros ≤ 2 decimals; purchase reduces cash by qty×cost; trade adds sold×price; never negative. **R4** gross profit = revenue − cost of units sold; overall = final cash + stock at cost − 100. **R5** each day recorded once; refresh/reopen must not repeat sales; one trade = one day.
- Acceptance: A1 buy 10×€2 → cash 80, stock 10; extra €82 rejected · A2 ref €4: €4→10, €4.01→5, €8→5, €8.01→0; price ≤0 rejected · A3 trade 10 units at €4 → revenue 40, COGS 20, profit 20, cash 120, stock 0 · A4 3 units vs demand 10 → sell 3; 0 stock → 0 · A5 restart keeps everything, one record per day · A6 after day 5 disabled; confirm new run resets, cancel preserves.

### 7.3 Festival Architect — 2 stages · 8 artists · €10,000
One day, 14:00–23:00. Artists: name, genre, fee > 0, fixed duration (minutes). Catalogue allows ≥4 bookings within budget.
- **FA01** browse artists (genre, fee, duration; booked marked). **FA02** schedule: stage + start time, end computed; explain rejections. **FA03** plan by stage in time order; total fees + remaining budget. **FA04** edit stage/start or remove; invalid edit keeps original. **FA05** finalise only with ≥4 artists and all rules passing; final is read-only until reopened as draft.
- Rules: **R1** each artist once; fee once; removal releases fee. **R2** start ≥14:00, end ≤23:00; no overlap on same stage; back-to-back allowed. **R3** simultaneous on different stages OK. **R4** total ≤ €10,000 (exactly full allowed). **R5** edits are replacements; final plan can't change.
- Acceptance: A1 Stage A 16:00–17:00, second 16:30–17:15 rejected, 17:00 accepted · A2 same time different stages OK · A3 60-min set: 13:59 and 22:01 rejected, 22:00 OK · A4 with €9,000 committed: €1,000 OK, €1,001 rejected; duplicate artist rejected · A5 conflicting edit keeps original; valid edit no duplication; remove frees slot+fee · A6 persists after reopen; finalise with 3 rejected, 4 OK; stays read-only after reopen.

---

## 8. Final checklist before the deadline (2026-11-23 23:59)

- [ ] App deployed at a public URL, latest `main` live, data persists as intended (check temporary-disk issue).
- [ ] All workflows work, including invalid input (clear error messages, no crashes).
- [ ] Tests cover accepted + rejected actions + edge cases; `uv run pytest` green on `main`.
- [ ] External API / AI failures handled gracefully; tests use fakes.
- [ ] No secrets in repo or history; `.gitignore` covers `.env` / `.streamlit/secrets.toml`; `.env.example` present; secrets set in host.
- [ ] Access control enforced server-side (if accounts/roles); input validation in `logic.py`.
- [ ] Dependencies minimal and pinned (`pyproject.toml` + `uv.lock`).
- [ ] Repo **public**; `README.md` has URL, member names + student numbers, run & test commands.
- [ ] Every member has commits and can explain every part (where data is stored, what tests cover/don't, what happens if the API is down, why it was built this way, limits).
- [ ] Demo accounts per role prepared; open the URL before presenting so the app is awake; hosted DB not paused.
