# Group Decision App – Feature Concept

Working title: **Einig** (name still open)
Status: November 2026 · Purpose: starting point for implementation in the programming course

---

## 1. The idea in one sentence

A web app that helps groups decide quickly and fairly what to do. Instead of picking the option most people like, it picks the one everyone can live with, and on request it suggests suitable or deliberately new places nearby.

## 2. Problem and unique selling point

Group decisions ("Where are we going on Saturday?") often fizzle out in group chats, and the same people tend to get their way while others quietly go along unhappy. Existing restaurant swipe apps only look for matches and use a simple yes/no.

This app differs in five ways:

1. **Three-level rating** ("Rather yes" / "Fine with me" / "Rather not") makes compromises visible.
2. **Fair winner selection:** rejection weighs more heavily than approval.
3. **Fairness memory:** whoever gave in last time gets more weight next time.
4. **Fair meeting point:** places are searched around the group's midpoint, not one person's location.
5. **Surprise mode incl. Blind Date:** the app deliberately suggests new places, optionally without name and photo.

## 3. Terms

| Term | Meaning |
|---|---|
| Room | A single decision, e.g. "Dinner on Friday". Has options, participants and a result. |
| Group | A fixed circle (flatmates, friends) that uses several rooms over time. Optional. |
| Participant | A person in a room, identified by nickname and session token, no account. |
| Option | One choice, either entered manually or a place from Google Maps. |
| Rating | A participant's vote on an option (three levels). |
| Joker | One veto per participant and room that reliably excludes an option. |
| Creator | The participant who created the room and configures it. |

## 4. User flow (standard case)

1. Creator sets up a room: title, mode (manual / places nearby / surprise), optional deadline.
2. The app generates an invite link and a QR code.
3. Participants open the link, choose a nickname and optionally share their location.
4. Options are collected: manually and/or automatically via Google Maps.
5. Everyone rates all options in their own random order and can use their joker once.
6. The room closes when everyone is done, the deadline is reached, or the creator closes it.
7. The app shows the winner (for places with map and route) and an anonymous summary.

---

## 5. Features by priority

Priority **M** = Must (minimum version for submission), **S** = Should (first extension), **C** = Could (bonus).

### 5.1 Core features (M)

**F1 – Create a room (M).** The creator sets a title and mode. The app generates a unique, hard-to-guess room ID (e.g. 8–10 characters). Done when a room is stored and an invite URL is returned.

**F2 – Join without an account (M).** Open the link, enter a nickname, store a session token in the browser so the participant is back in the room after a reload. Done when several devices can join the same room at once and duplicate nicknames are prevented.

**F3 – Add options manually (M).** All participants can add options as long as the rating phase hasn't started. Empty entries and duplicates are rejected.

**F4 – Three-level rating (M).** Each option is shown as a card and rated "Rather yes", "Fine with me" or "Rather not" (buttons, optionally swipe gestures). Each person sees the options in their own random order so the first card isn't systematically favoured. Individual votes are never visible to others.

**F5 – Fair winner selection (M).** See the algorithm in section 6.

**F6 – Result view (M).** Winner plus anonymous distribution per option (e.g. "3× rather yes, 1× fine with me"). Who voted for what is never shown.

**F7 – Room status updates (M).** For the minimum version the page polls the status every 3–5 seconds: who has joined, who is done, whether the room is closed.

### 5.2 Places from Google Maps (S)

**F8 – Suggest places nearby (S).** The creator picks a category (restaurant, bar, café, cinema …), a radius and optional filters: price level, minimum rating, "open at the planned time". The backend queries the Places API (New) via Nearby Search and creates the results as options (recommended: 10–15). Each card shows name, photo, rating, price level and distance.

**F9 – Map and route to the winner (S).** After the decision a map (Maps JavaScript API) shows the winner, plus an "Open route in Google Maps" link.

**F10 – Joker / veto (S).** Each participant has exactly one joker per room. An option with at least one veto is excluded. If this excludes everything, the option with the fewest vetoes wins, then the best score.

**F11 – Deadline (S).** Optional countdown (e.g. 15 / 30 / 60 minutes), after which the room closes automatically. Participants who haven't voted are not counted.

### 5.3 Surprise mode (S)

**F12 – Guided randomness (S).** The group sets the main category (e.g. "any new restaurant") plus optional price range, minimum rating and radius. The app runs several small searches with different subcategories (e.g. different cuisines), mixes the results and picks a varied selection, ideally no two options from the same subcategory. Already known places (F13, F17) are excluded. If there are too few results, the app gradually widens the radius (e.g. +50 %, at most three times) and tells the group.

**F13 – "Been there" (S).** Button on every card in surprise mode. The place is replaced with a new one for everyone and, if there is a fixed group, marked as known in its history.

**F14 – Blind Date variant (C).** Cards show only cuisine/category, price level, distance and rating, but no name and no photo. Name, photo and map are revealed only after the decision.

**F15 – Fate mode (C).** No voting: the app picks one place directly. Participants can only use their joker, after which the app rolls again.

### 5.4 Groups and fairness over time (C)

**F16 – Fixed groups (C).** A group has its own invite link. Members are recognised via a token stored in the browser. Rooms can be assigned to a group.

**F17 – History (C).** For each group, places that won (place ID and date only) and "Been there" marks are stored. This is the basis for surprise mode.

**F18 – Fairness memory (C).** A personal weight per group member that adjusts after each decision (see 6.3).

### 5.5 Fair meeting point (C)

**F19 – Search around the group's midpoint (C).** Participants voluntarily share a rounded location. The app calculates the geographic midpoint (averaging coordinates is sufficient at city distances) and searches there. Without shared locations, the creator's location or an entered address is used.

**F20 – Fair travel times (C).** Using the Routes API, the app calculates each participant's travel time to each place. Places where the longest trip is well above the group average (e.g. more than 1.5×) are filtered out or flagged.

### 5.6 Technical bonus (C)

**F21 – Live updates via WebSocket (C)** instead of polling.
**F22 – QR code display** for joining at the same table (easy to build, closer to S than C).

---

## 6. Winner selection algorithm

### 6.1 Points per rating

| Rating | Points |
|---|---|
| Rather yes | +2 |
| Fine with me | +1 |
| Rather not | −4 |

The strong negative weight ensures that an option with a clear "Rather not" usually ranks behind an option everyone can live with. Define the values as constants so they are easy to tweak and to justify with examples in the course.

### 6.2 Procedure

1. Exclude options with at least one veto (joker).
2. For each remaining option: `Score = Σ (weight_i × points_i)` across all participants who voted. Without group fairness, `weight_i = 1`.
3. The highest score wins.
4. Break ties in this order: fewer "Rather not", then more "Rather yes", then random.

### 6.3 Fairness memory (fixed groups only)

Each group member has a weight, starting at 1.0. After each decision it is adjusted based on the member's own rating of the winner:

| Own rating of the winner | Adjustment |
|---|---|
| Rather not | +0.3 |
| Fine with me | +0.1 |
| Rather yes | reset to 1.0 |

The weight is capped at 1.6. Members who didn't vote stay unchanged. The result only states in general terms that fairness weights were applied, not whose.

### 6.4 Test cases (for unit tests)

| Case | Expected |
|---|---|
| Option A: 3× yes, 1× not · Option B: 4× fine | B wins (A: 2, B: 4) |
| Same score, A has one "not", B has none | B wins |
| Every option has a veto | Option with fewest vetoes, then best score |
| Only one person voted | Their best option wins |
| Nobody voted | No winner, show a message |

---

## 7. Data model (draft)

| Entity | Key fields |
|---|---|
| Group | id, name, invite_token, created_at |
| GroupMember | id, group_id, nickname, member_token, fairness_weight |
| Room | id, group_id (optional), title, mode (manual / nearby / surprise / blind / fate), status (collecting / voting / closed), deadline, search_center_lat/lng, radius_m, filters (JSON), winner_option_id, created_at |
| Participant | id, room_id, group_member_id (optional), nickname, session_token, approx_lat/lng (optional, rounded), has_finished, veto_used |
| Option | id, room_id, source (manual / google), label, place_id (optional), category, is_replaced |
| Vote | id, room_id, participant_id, option_id, rating (yes / ok / no) – unique per participant and option |
| Veto | id, room_id, participant_id, option_id – at most one per participant and room |
| GroupPlaceHistory | id, group_id, place_id, reason (won / known), date |

Note: for Google places, only the place ID is stored permanently. Name, photo, rating etc. are loaded fresh when displayed (Google terms of service).

---

## 8. Backend endpoints (draft)

| Method | Path | Purpose |
|---|---|---|
| POST | /api/rooms | Create a room |
| GET | /api/rooms/{id} | Get room status (for polling) |
| POST | /api/rooms/{id}/join | Join, returns session token |
| POST | /api/rooms/{id}/options | Add an option manually |
| POST | /api/rooms/{id}/suggest | Fetch places from Google Maps (normal or surprise) |
| POST | /api/rooms/{id}/options/{optionId}/replace | "Been there", replace option |
| POST | /api/rooms/{id}/start | Start rating phase (creator only) |
| POST | /api/rooms/{id}/votes | Submit a rating |
| POST | /api/rooms/{id}/veto | Use the joker |
| POST | /api/rooms/{id}/close | Close the room and compute the winner |
| GET | /api/rooms/{id}/result | Get the result |
| POST | /api/groups | Create a group (C) |

Every write request checks the session token so nobody can vote on someone else's behalf.

---

## 9. Google Maps integration

**Services used:** Places API (New) with Nearby Search, Place Details and Place Photos; Maps JavaScript API for the map; Routes API only for F20.

**Key implementation rules:**

- Places queries run exclusively through the backend. The API key lives in an environment variable and never in frontend code or the Git repository.
- In the Google Cloud Console, restrict the key to the APIs used and, for the in-browser map, to your own domain.
- Use field masks: request only the fields you actually display, because billing is based on the most expensive field requested.
- One search per room, not per participant.
- Costs (as of Nov 2026): free monthly quotas per service, 5,000 calls for Nearby Search Pro, then $32 per 1,000. The free quota is enough for a course project. A Google Cloud account with a payment method is required.
- Display Google attribution as required by the terms of service.

**Fallback without a Google account:** OpenStreetMap via the Overpass API and Leaflet for the map, free, but without ratings and photos.

---

## 10. Privacy

- No account, no email, nicknames only.
- Location sharing only after active consent, stored rounded to roughly 300–500 m.
- Location data is deleted as soon as the room is closed.
- Individual votes are never visible to other participants, not even the creator.
- Rooms without a group are deleted automatically after a fixed period (e.g. 7 days).

---

## 11. Tech stack (suggestion, depends on course requirements)

| Layer | Python variant | JavaScript variant |
|---|---|---|
| Backend | Flask or FastAPI | Node.js with Express |
| Database | SQLite (later PostgreSQL) | SQLite (later PostgreSQL) |
| Frontend | HTML, CSS, vanilla JavaScript or React | React or vanilla JavaScript |
| Map | Maps JavaScript API | Maps JavaScript API |
| Tests | pytest for the winner algorithm | Jest for the winner algorithm |
| Hosting (demo) | Render, Railway or similar | Render, Railway, Vercel or similar |

---

## 12. Suggested implementation order

1. **Sprint 1 – Foundation:** data model, F1, F2, F3, F7.
2. **Sprint 2 – Voting:** F4, F5 with unit tests, F6. This completes the minimum version.
3. **Sprint 3 – Places:** F8, F9, F22.
4. **Sprint 4 – Excitement:** F10, F11, F12, F13.
5. **Sprint 5 – Bonus:** F14, F15, F16–F18, F19–F21, depending on remaining time.

---

## 13. Open questions

- Programming language and framework per course requirements
- Course scope requirements (mandatory features, team size, submission format)
- Final app name
- Google Maps or OpenStreetMap as the data source
- Fine-tuning the point values and fairness adjustments based on test runs
