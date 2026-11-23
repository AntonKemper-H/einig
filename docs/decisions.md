# Team decisions

Decisions the team has made so far, with the reason for each. When a decision changes, update this file and `AGENTS.md` in the same pull request.

Last updated: 2026-11-18

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
  - **Update 2026-11-16:** the account is in Google Cloud's free trial, where quotas cannot be lowered, so there is no daily quota for now. The trial limits the cost instead: usage is paid from the trial credit, and Google stops the APIs when the credit is used up instead of charging money. **Never upgrade to a paid account before a daily quota is set.** The budget alert (€1, 50/80/100 %) covers the project with all services, so any spending sends an email; a spending cap is not possible because it does not support the Maps APIs. If the credit were used up (e.g. through a leaked key), the Places features would stop and the group would continue with manual options. To make that unlikely, the server key is restricted to Places API (New) and never appears in a page.
- **Key handling:** only in local `.env` and the host's secret settings. Shared privately between members. Never in the repo, in code, or in a chat with an AI. If leaked: delete the key in Google Cloud Console immediately and create a new one.
- Tests never call Google (fake responses). Members without a key can still work and test.
- If Google fails: friendly message; for 10 minutes the group can add options as text (D23).

## D7 – Scope

Concept priorities M/S/C apply, with this cut for the submission:

| Build now | Parked (only after the core works and is deployed) |
|---|---|
| F1–F7 minimum version | F14 Blind Date |
| F8–F11 places, map, joker, deadline | F15 Fate mode |
| F12–F13 surprise mode, "been there" | F18 fairness memory |
| F23 find a place by name, F24 delete an option (D14) | F17 group history (D15) |
| F25 my rooms, F16 fixed groups (D15) | F26 place collection and map (D15, not built for the submission) |
| F27 room setup, F28 hidden collecting, room page layout (D17) | |
| F22 QR code | F19 meeting point, F20 travel times, F21 WebSockets |
| F29 share and save the result (D18) | |

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

## D13 – `segno` for the QR code (2026-11-15)

- New dependency `segno==1.6.6`, pinned in `pyproject.toml` and `uv.lock`, for the QR code of the invite link (F22, A6, PR #16).
- **Why:** JavaScript is only allowed in three fixed files (`AGENTS.md`), so the QR code has to be drawn on the server. `segno` is pure Python with no further dependencies and writes the code as SVG text, which goes straight into the page: no image library (e.g. Pillow), no image file, no external QR service (privacy: no external resources).
- **Not chosen:** a JavaScript QR library (not allowed), an online QR API (sends the invite link to a third party).
- Approved by AntonKemper-H on 2026-11-15, as `AGENTS.md` asks before adding a dependency. The team confirms it with the review of PR #16.

## D14 – Find a place by name (F23) and delete an option (F24) (2026-11-16)

Two features that are not in `docs/concept.md`, added to the scope (D7) because manual options have two gaps: a typed name gives no card (no photo, rating or map), and a typo or a joke entry can never be removed.

**F23 – Find a place by name (S).** A participant types a name (e.g. "Luigi's") and picks the right place from a short list of matches; it is saved as a Google option with a normal card (C2b).
- **No JavaScript:** two steps with plain forms (AGENTS.md allows no autocomplete script). Step 1: the name is sent, the server runs **one** Text Search (New) and shows at most 5 matches with name and address. Step 2: the participant picks one and saves it.
- **Only the place id is stored.** Names and addresses of the matches are shown once and never written to the database (Google terms, as in C2). The ids of the shown matches are kept in the signed session cookie until the choice, and only those ids are accepted, so no other place id can be posted and no second Google call is needed.
- **Location:** the search prefers the room's search centre if it has one (`nearby`, `surprise`); otherwise the participant can tap "Use my location" (`geolocation.js`, unchanged), or it searches without a location.
- **Who and when:** every joined participant, in every room mode, only while the room is `collecting` (like adding options). A place that is already an option of the room is rejected with a message.
- **Cost:** field mask `places.id,places.displayName,places.formattedAddress`. Because of `displayName` this is billed as Text Search **Pro**, which Google lists with 5,000 free requests per month; with only `places.id` it would be free, but then nobody could see which match is the right one. One call per search, plus the card details every Google option already costs. During the free trial (D6) this is paid from the trial credit. The C6 spec decides whether a limit of searches per room is needed.
- **Exception to "one search per room"** (AGENTS.md): this search is per participant, because every person adds their own places.
- Without a key, on any Google error or without matches: a friendly message, and the typed text can still be added as a manual option.

**F24 – Delete an option (S).** An option can be deleted by **the participant who added it** or by **the room creator**.
- **Only while collecting.** Deleting during voting would throw away other people's ratings.
- Options from the "Places nearby" and "Surprise me" searches have no author (the search adds them for the group), so only the creator can delete them. "Been there" (F13) stays the way for everyone to swap a surprise place.
- Checked on the server: hiding the button is not a permission check. Deleting an option that is already gone (e.g. two presses at once) changes nothing and is ignored.
- Who added an option is never shown to others; it is only used for the permission check.
- **Schema change** (owner: Track A, D10), decided in the A7 spec: a new table `option_authors (option_id, room_id, participant_id)` instead of a column `options.added_by`. A reviewed C5 test checks the exact columns of `options`, and `init-db` adds a new table to the deployed database by itself (`CREATE TABLE IF NOT EXISTS`), with no `ALTER TABLE` and no `reset-db`. Search results have no row. A place found by name (F23, C6) gets a row for the participant who saved it.

**Tasks:** C6 F23 (Track C, mkim-nova) and A7 F24 (Track A, owns the schema). Both follow D9: own spec, tests reviewed before the implementation.

**Why now and not parked:** both make the core flow (F3) usable in a real group, unlike the parked extras F14–F21. If time runs short, F24 comes first: it is smaller and fixes mistakes that otherwise stay in the room until the end.

## D15 – My rooms (F25), fixed groups (F16) and a place collection with a map (F26) (2026-11-16)

Three features that turn single decisions into something a group comes back to: the home page lists every room this phone is in, a group can plan one activity after another without everyone joining again, and every person collects the places they have actually been to, on a map. F25 and F26 are not in `docs/concept.md`; this decision describes them. F16 is in the concept (parked in D7) and is moved into the scope here, in the reduced form below.

**F25 – My rooms (S).** The home page lists the rooms this browser has joined, newest first, with title, status and a link to the right page; a link "My rooms" in the header leads back from every page.
- **No accounts, no new table:** the list comes from the room tokens already stored in the signed session cookie (A3).
- **The cookie now lasts 180 days** (`session.permanent = True`, `PERMANENT_SESSION_LIFETIME`). Until now it ended when the browser closed, which would empty the list and the place collection. The cookie still holds only random tokens.
- **The cookie stays small:** tokens of rooms that no longer exist are dropped, and at most 30 rooms are remembered (browsers refuse cookies over about 4 KB, which would lose everything). Rooms are deleted after 7 days anyway.

**F16 – Fixed groups (S, reduced).** A group has a name and its own invite link and QR code. Members join once with a nickname; a member token in the cookie recognises them.
- On the group page every member can **plan a new activity**: a new room (title and mode) that belongs to the group. Members open it and join with **one tap** under their group nickname; nobody types a name again.
- Guests who are not in the group can still join a group room with the room link, like any other room.
- The home page lists the groups above the rooms.
- **Not included:** the fairness memory (F18 stays parked), renaming or removing members, leaving a group, group admins. Every member has the same rights.
- **Schema change** (owner: Track A, D10): new tables `groups`, `group_members`, `group_rooms` (room → group) and `group_participants` (room participant → group member). Like A7's `option_authors` (D14), only new tables and no new columns, so `init-db` adds them to the deployed database by itself.
- Groups are deleted 90 days after their last new room (rule for the cleanup command; the command itself is not part of these tasks and is not built yet, see AGENTS.md).

**F26 – Place collection and map (S).** A small game: every person collects the places they have really been to and sees them as pins on their own map.
- **"I was there":** on the result page of a closed room whose winner is a Google place, every participant can press "I was there ✓". Only then is the place collected, because a winner is not always where the group really went. Manual options cannot be collected (no place id, no location).
- **A person, not an account:** the collection belongs to a random `person_token` in the cookie, created at the first "I was there". Losing the cookie loses the collection; moving it to another phone is not part of this decision.
- **Stored:** only person token, place id, room id, group id (if any), whether the room was a "Surprise me" room, and the date (Google terms: only the place id is ours to keep). The table is not linked to the room, so a visit stays when the room is deleted after 7 days. Visits are deleted 180 days after the date (rule for the cleanup command), the same as the cookie: once the cookie is gone, nobody can see them any more, so keeping them longer would only store data (review of PR #41).
- **"My places" page:** the number of collected places, badges (e.g. "First place", "Explorer" for 10 places, "Surprise hunter" for 3 places from surprise mode, with the progress to the next one) and the places as cards (C2b).
- **Group map:** the group page shows every place that someone collected in one of the group's rooms (members or guests). Who was there is never shown, only the places.
- **The map without JavaScript:** a picture from the **Maps Static API** with one pin per place; Google fits the view to the pins. It is loaded by the server through a proxy route (like the photos), so the key never appears in HTML. The Embed map (C3) cannot show more than one place, and the Maps JavaScript API would need a script, which AGENTS.md does not allow.
- **Cost:** a map picture needs the location of each pin. Locations are loaded fresh (field mask `location` only, Place Details Essentials) and never stored. At most 25 pins per map, the picture is cached in the browser for 10 minutes. Static Maps and Place Details Essentials each list 10,000 free requests per month. The Maps Static API must be enabled in Google Cloud and allowed for `GOOGLE_MAPS_API_KEY` (mkim-nova).
- **Exception to "one search per room"** (AGENTS.md): the map and the "My places" cards load details per person and per group, not per room.

**Tasks** (each with its own spec and branch, D9), in this order:

| Task | Feature | Track | Needs |
|---|---|---|---|
| A8 | F25 My rooms | A | – |
| A9 | F16 Fixed groups | A (schema) | A8 merged (home page); new tables only, like A7 |
| C7 | F26 "I was there" and "My places" | C (schema change reviewed by Track A) | A9 merged (`group_rooms`) |
| C8 | F26 Map of my places and of a group | C | C7 merged |

**Why now and not parked:** the result page is the end of the current app; these features give a reason to open it again, and the demo can show a group planning its second evening. If time runs short, cut from the end of the table: A8 alone is already useful, C8 is the first to go.

**Update 2026-11-21:** C7 and C8 (F26) are not built for the submission. A8 and A9 are done; the remaining days go to C10, bug fixes, the README and the demo. The specs stay in `specs/` for later.

## D16 – Swipe to rate (F4) and a menu link on the rating card (2026-11-16)

F4 in `docs/concept.md` says "buttons, optionally swipe gestures". With the place cards on the rating page (C2c), rating can feel like the swipe apps people know: drag the card right, up or left. Swiping needs JavaScript, so this decision changes two rules in AGENTS.md.

- **Swipe on top of the buttons, never instead of them.** A new file `app/static/js/swipe.js` lets the participant drag the card; when it is let go far enough, the script presses the matching rating button that is already on the page. The form, the route, the rules and the server tests do not change. Without JavaScript, with a screen reader, or for anyone who prefers tapping, the three buttons work as before.
- **Three directions for three ratings:** right = "Rather yes", up = "Fine with me", left = "Rather not". While dragging, the card shows which rating it would give. Below a minimum distance the card springs back and nothing is sent, because "Rather not" weighs −4 and a slip must not count. Ratings can still be changed on the overview page (B2).
- **Only one card at a time** (the next unrated option). The overview page, where every option is listed, keeps buttons only.
- **Menu link:** the rating card gets a link "Menu & reviews on Google Maps" to the place's Google Maps page, where the menu tab is. It is a normal Maps URL built from the place id (like the route link in C3): no key, no API call. Google offers no reliable menu photo through the Places API, so a link is what is possible.
- **Tests:** pytest cannot test a finger gesture. The tests check that the page includes the script and the hints, and that the buttons still work; the gesture itself is tested by hand on an iPhone and an Android phone and written down in the pull request. Update 2026-11-18: A10 counts as done after the check on one iPhone in Safari (#58), because the gesture uses only standard Pointer Events and the buttons stay as the fallback. The Android Chrome check is done later by whoever on the team has an Android phone, and `docs/plan.md` says it is still open until then.
- **Walkthrough:** the script is kept short and commented, because every team member must be able to explain it.

**Task:** A10 (Track A, AntonKemper-H), own spec `specs/a10-swipe-rating.md`, built after C2c is merged. If time runs short, it is dropped without loss: the buttons are the complete feature.

## D17 – Room setup (F27), a calmer room page and hidden collecting (F28) (2026-11-16)

Feedback from clicking through the app: the room page is long (invite link twice, every place as a full card), the separate lobby is an extra step, the creator cannot say what kind of activity the room is about, and everyone sees everyone's ideas while collecting, which pushes people to copy instead of suggesting their own. F27 and F28 are not in `docs/concept.md`; this decision describes them.

**F27 – Room setup (S).** While the room is `collecting`, the creator sets up:
- **Activity and kind**, from a two-level catalogue in `app/services/activities.py`: Food (breakfast, brunch, restaurant), Drinks & café (bar, café, dessert), Sport (bowling, climbing, swimming, fitness, sports ground), Culture & leisure (cinema, museum and gallery, theatre, amusement park and zoo, park and hiking). Each kind maps to Google place types; "Places nearby" and "Surprise me" search with the kind's types instead of the creator choosing a category in the search form. Only types that exist in Google's place type table are used.
- **Lunch or dinner** is not a Google type; it would need opening hours and is not part of F27. "Restaurant" covers both.
- **Options per person** (1–5 or unlimited): how many own options each participant may add. Places from the Google searches do not count; places a participant found by name (C6) do. Uses the authors in `option_authors` (A7, D14).
- **Changeable while collecting, fixed once voting starts**, so the basis of the ratings never moves.
- **Stored in a new table `room_setups`** (one row per room), not in new columns of `rooms`: like `option_authors` (A7), `init-db` creates a new table on the deployed database by itself, without `ALTER TABLE`. The table also holds the two F28 choices below (`hide_ideas`, `reveal_places`), so A11 needs no second schema change.
- **Groups:** every new activity in a group (A9) gets its own setup, with the same form. There is no group admin and no stored group default.
- Rooms without a setup work exactly as today, so every existing test and room stays valid.

**Room page layout (design task).** One page instead of room page + lobby:
- Participants as a collapsible list (`<details>`, no JavaScript) with the "done" marks and, for the creator, "Start voting". On a wide screen it sits at the side, on a phone at the top.
- Options as a compact list of names; a Google place opens its card when tapped (`<details>`).
- Invite link and QR code at the end of the page.
- **The lobby stays as the waiting page:** the room page cannot reload itself (it would wipe what someone is typing), and only a reloading page shows live without JavaScript when the voting starts. The room page links to it as "I'm done – wait for the others". The lobby tests stay unchanged.
- **Invite link:** `tests/test_proxy_headers.py` checks both the text field and the link. Decided in the review of this decision: both stay, in one compact block, and the reviewed test helper (`invite_urls_in`) is not changed.

**F28 – Hidden collecting (S).** While collecting, every participant sees only the options they added themselves; everything is revealed on the rating cards when the voting starts.
- **A setup choice, on by default in the setup form:** "Keep everyone's ideas secret until voting". Rooms without a setup (and rooms where the creator turns it off) show all options as today, because a reviewed test (`test_options.py`) checks that participants see each other's options.
- **Places from the Google searches** are a setup choice: "show suggested places to everyone while collecting" (then "Been there" works as today) or "keep them secret until voting" (full surprise, no "Been there").
- Instead of the others' options, the page shows how many there are ("Others have added 4 options"), so the group still sees progress.
- A name someone else already added is rejected with `Someone already had the same idea – it is already in the room.`, which reveals nothing more than that.
- The creator sees only their own options as well; deleting other people's options (F24) is therefore not possible in a room with hidden collecting.
- **Accepted trade-off:** in a hidden room nobody can remove someone else's typo or joke entry before the voting starts (collecting is the only time deleting works, and the reason for F24 in D14). The group can still rate it down. A creator who wants to clean up turns hidden collecting off for a moment, which shows all options **to everyone, not only to the creator** (the surprise is gone for the ideas seen so far) and allows deleting again.
- Who added an option is never shown, also not after the reveal (as D14).

**Tasks** (own spec and branch each, D9), in this order; cut from the end if time runs short:

| Task | Feature | Track (proposal) | Needs |
|---|---|---|---|
| C9 | F27 Room setup | C (catalogue and searches; new table reviewed by Track A) | A7 (merged), C6 merged (#39; C9 puts C6's "save a place by name" under the per-person limit) |
| B6 | Room page layout | B (Timonhio) | C9 merged (setup form on the page); starts only after B4 and B5 |
| A11 | F28 Hidden collecting | A | C9 and B6 merged |

## D18 – Share and save the result (F29) (2026-11-16)

After the vote the group has a winner, but the app stops there: someone still has to copy the name into the group chat and put the date into a calendar. F29 closes that gap with two buttons on the result page. Like the route link in C3, both are plain links and a downloaded file: no new API, no key, no new dependency, no JavaScript.

**F29 – Share and save the result (S).** On the result page of a closed room with a winner, every participant sees:
- **"Share in WhatsApp"**: a normal link to `https://wa.me/?text=…` with a ready-made message, e.g. "Dinner on Friday: we're going to Pizza Roma! Route: <Google Maps route link>". WhatsApp opens (app on the phone, WhatsApp Web on a laptop) and the person picks the chat. The app sends nothing itself.
- **"Add to calendar"**: a small form with a date and a time (plain `<input type="date">` and `<input type="time">`, defaults: today, next full hour). It downloads an `.ics` file that every calendar app opens (iPhone, Android, Google, Outlook): title "<room title>: <winner>", the place name, the Google Maps link, 2 hours long.

Rules:
- **Nothing new is stored.** The message and the file are built when the button is pressed; the date and time are not saved. No schema change.
- **Privacy:** the message and the file contain only the room title, the winner's name and the route link. No nicknames, no counts, no jokers, and never the invite link. Who shares it with whom is up to the person.
- **Google terms:** the winner's name comes fresh from Place Details, as on the result page (C3, C2c); it is not written to the database. A manual winner has no place id, so its message and file have no route link.
- **Who and when:** only joined participants of the room, only when the room is `closed` and has a winner. Otherwise there is no button, and the `.ics` route answers like the result page (visitors to the join form, no winner → a message).
- **Time zone:** the entered time is read as Europe/Lisbon time and written to the file in UTC (`DTSTART:…Z`), so every calendar app shows the right time, also across summer time (`zoneinfo` from the standard library). Only if the server has no time-zone data does the file fall back to "floating" local time. *(Changed in B7 after the review of #45: a file without a time zone often ends up an hour off.)*
- **Code:** two pure helpers in `app/services/` (build the WhatsApp text and link; build the `.ics` text with correct escaping, CRLF line endings and line folding), both unit-tested; the route stays thin. Only the Python standard library (`urllib.parse`, `datetime`).

**Task:** B7 F29 (Track B, Timonhio), own spec `specs/b7-share-result.md`, tests reviewed before the implementation (D9). It comes after B4 and B5. If time runs short it is dropped without loss: the result page is complete without it.

**Why:** it is small, it works without new risk, everyone understands it in the live demo at once, and it turns "we decided" into "we are actually going".

## D19 – Know what a place is: kind, reviews and more on the back of the rating card (F30) (2026-11-18)

Feedback from testing: a Google suggestion shows a name, one photo and "4.5 ★ · €€ · 330 m". Often nobody can tell what kind of place it is, and the first photo Google sends may show a door or a menu board instead of the food. To make a real decision, people need the kind of place, how many people rated it, a few reviews and more photos. F30 is not in `docs/concept.md`; this decision describes it.

**F30 – Place details on the rating card (S).** Two parts:
- **Front of every place card:** the kind of place from Google (`primaryTypeDisplayName`, e.g. "Italian Restaurant") above the facts, and the number of ratings next to the stars ("4.5 ★ (812)"). Cards ask for these two extra fields with a new field mask; the existing details call and its reviewed tests stay exactly as they are.
- **Back of the rating card (on the one-card rating page only):** tapping the card turns it over. The back shows Google's short description of the place (when Google has one), up to 3 reviews with stars, age, author and a link to the review on Google Maps, what the place offers ("Vegetarian · Cocktails · Good for groups") and up to 3 more photos. The "Menu & reviews on Google Maps" link (A10) stays visible below the card on both sides.
- **No AI review summary:** Google's review summaries are not offered for Portugal, and showing one needs a heading, a disclosure text and three extra links. The short description (`editorialSummary`) is used instead.
- **No JavaScript needed to turn the card:** a visually hidden but focusable checkbox and two labels switch front and back with CSS, also with the keyboard. `swipe.js` (A10) also turns the card on a short tap without movement, so tapping the card itself works; a drag of 110 px or more still rates, and a touch that starts on a link does neither.
- **The 3D flip animation and the look of both sides are design work** and are done in the general design phase at the end; F30 only switches between the two sides.
- **Cost:** reviews and the "serves" fields are in Google's most expensive tier of Place Details. They are loaded **only for the one card on the rating page**, in the same single call as its front (so still one call per rating step, as C2c), never on the room page, the overview, the result page or in lists. The two front fields may move the card calls to a higher tier too. The implementation PR names the tiers and the free amounts from Google's current price list (budget alert D6 stays).
- **Google terms:** each review is shown unchanged with its author's name, photo and profile link and a link to the review on Google Maps; the "Google Maps" attribution stays. Nothing of it is stored (as every Google field except the place id).
- **No menu photo:** Google does not mark which photos show food or the menu, so the app cannot pick one. More photos and the Google Maps link are what is possible.

**Task:** C10 F30 (Track C, mkim-nova), own spec `specs/c10-place-details.md`, after A10 and C2c (both merged). Before C8 in the plan, because it helps the decision itself, which is the point of the app. If time runs short, the front part alone is already useful.

## D20 – The rating card fills the screen: swipe on the front, pages on the back, no buttons in sight (F4, F30) (2026-11-21)

Feedback from testing C10 on a phone: the page with the turned card gets long and confusing, and the three buttons below the card use space the card needs. The rating page should show **only the card**, filling the screen, with nothing to scroll.

**What changes (supersedes parts of D16; D19's turning stays):**
- **The card fills the screen** on the one-card rating page. The page itself does not scroll. The overview after the last card keeps its normal page.
- **Front: swipe to rate.** Right = "Rather yes", up = "Fine with me", left = "Rather not" (as D16), and **down = joker**. A mouse works the same way by dragging. A tap on the card turns it over (D19).
- **Back: no rating, only information.** You cannot rate on the back; to rate, turn the card back with a tap on it. Sideways swiping on the back changes between **three pages**, shown by three dots at the bottom: **1. About** (description, offers and the "Menu & reviews on Google Maps" link), **2. Photos**, **3. Reviews**. Inside a page, content that is too long scrolls inside the card; the card stays where it is. So left and right never mean two things at once: rating gestures exist only on the front, page changes only on the back.
- **Joker by swiping down:** because the joker cannot be undone, a swipe down does not use it at once. It opens a short question "Use my joker on <name>? This cannot be undone." with "Use joker" and "Cancel". "Use joker" presses the existing joker button.
- **The rating buttons and the joker button stay in the page, but out of sight** (visually hidden, still focusable, shown while they have the keyboard focus). So rating also works with the keyboard, with a screen reader and without JavaScript, and the server side does not change at all. This keeps the rule of D16 that the buttons stay, only invisible while swiping works.
- **Without JavaScript** the labels turn the card (as C10) and the dots on the back are links that change the page (CSS scroll snapping); rating works with the hidden buttons.
- **The creator's "Close the room" button and the link back to the lobby** must stay reachable without scrolling the card page. How is decided in the spec review of C11.
- **Allowed JavaScript:** `swipe.js` may grow to cover the joker question, the page dots and the tap on the back. No new file, no library.

**Task:** C11 (Track C, mkim-nova), own spec `specs/c11-fullscreen-card.md`, after C10 is merged. The turning from C10 stays, so most C10 tests stay true; the spec names the few that change.

## D21 – Design phase: one look for the whole app, on its own branch (2026-11-22)

D16, D19 and D20 left the look of the app to a design phase. All features for the submission are merged, so the design phase starts now.

- **Look:** a dark blue background, lighter blue buttons, white text, white cards and the "Einig" logo with two coloured i-dots. One theme for light and dark mode. The agreed draft is shared in the team.
- **Only the front end changes:** templates, `app.css`, the logo, and in `swipe.js` only a stamp while dragging. No route, form, scoring rule or database change. Swiping works exactly as today.
- **Reviewed tests stay unchanged.** Where a test pins a text or an order, the new layout keeps it in the HTML and changes only the visual order with CSS. Where that is not possible, the task stops and asks.
- **Own branch:** the work is done on `design` (from `main`). `main` and the deployed app stay as they are until the whole design is reviewed, then `design` is merged into `main` in one step, so one revert brings the old look back.
- **Three tasks:** D0 foundation (`specs/d0-design-foundation.md`) first; then D1a home, groups and room page (`specs/d1a-design-home-rooms.md`) and D1b rating card, lobby and result (`specs/d1b-design-vote-result.md`) in parallel. Each part is reviewed and tested by the person who did not build it.

## D22 – Remove a room from my list (F31) and delete a room (F32) (2026-11-22)

"My rooms" (F25) only grows: finished or mistaken rooms stay in the list, and a creator cannot get rid of a room made by accident. F31 and F32 are not in `docs/concept.md`; this decision describes them.

**F31 – Remove from my list (S).** Every tile of "My rooms" has a **Remove** button. It opens a short confirmation page (`GET /rooms/<id>/forget`, changes nothing); the removal is `POST /rooms/<id>/forget` (review of #85).
- It only removes the room's token from this browser's cookie. The database does not change: the participant, their ratings and jokers stay and still count, and the room stays for everyone else.
- The person cannot get back in as the same person: the token is the only proof of identity (no accounts, A3). Opening the invite link again means joining as a new participant. This is said once below the list and on the confirmation page, not on every tile.
- **A creator may remove an unfinished room** (collecting or voting) from their list. Then nobody can start the voting or close the room, so both warn: the list once below it (`In rooms you created, nobody else can start or close the voting.`, it refers to no single room) and the confirmation page for that room (`You are the creator: nobody else can start or close this room.`) We warn instead of forbidding it, because the creator who wants the room gone has F32. (Check in review.)

**F32 – Delete room (S).** Only the **creator**, in **any status**, deletes a room for everyone.
- Two steps without JavaScript: a confirmation page (`GET /rooms/<id>/delete`, deletes nothing) and `POST /rooms/<id>/delete`. After it the home page shows `Room "<title>" was deleted.`
- One `DELETE FROM rooms`; the `ON DELETE CASCADE` rules remove participants, options, ratings, jokers, authors, setup and the link to a group. **A group stays**, with its members.
- Not joined or not the creator: 403 and nothing changes. A room that is already gone: the POST redirects home, so deleting twice is harmless.
- Other participants lose the room from their list on their next visit of the home page (F25 already drops tokens of deleted rooms); the old link shows the 404 page.
- **No schema change.**

**Not included:** removing or deleting groups (they have members and a room history and need their own decision), restoring a deleted room, deleting several rooms at once.

**Task:** E3 (`specs/e3-remove-and-delete-rooms.md`, branch `feature-e3-remove-and-delete-rooms`), tests in `tests/test_remove_delete_rooms.py`.

## D23 – Typed options come back while Google Maps is unavailable (2026-11-23)

Since E1 (#80) every option comes from Google Maps. When Google cannot be used (no key, network down, trial credit used up), a group could no longer add any option, and the room was stuck. That breaks D6 ("the group continues") and the course's "External API failures handled gracefully".

- **What:** the typed field from before E1 comes back, **only as a fallback**. After a call to Google failed in the search by name (C6), places nearby (C2a), surprise (C4) or "Been there" (C5), or one of them found no server key, the room page shows `Add an option` again with the line `Google Maps is not reachable right now – you can add your idea as text.` `POST /rooms/<id>/options` then works exactly as before E1 (same checks, messages, F27 limit and F28 hidden ideas).
- **How long:** 10 minutes after the last failure; a successful Google call in one of these routes turns it off at once. Normally nothing changes compared with E1: no field, and the route answers 404.
- **Where the state lives:** in the app object (`app.extensions["google_unavailable_until"]`), no database or schema change. **Limit:** with several gunicorn workers each worker has its own state, so one worker may show the field a moment later than another. That is acceptable for a fallback.
- **The failed request itself** still answers with E1's page (the reviewed E1 tests pin that); the form appears from the next page load on.

**Task:** E5 (`specs/e5-typed-options-as-fallback.md`, branch `feature-e5-typed-fallback`), tests in `tests/test_typed_fallback.py`.

## Open questions

- Final app name.
- Final point values after test runs.
