# A9 – F16 Fixed groups: plan one activity after another

Branch: `feature-a9-groups`
Tests: `tests/test_groups.py` (rules), `tests/test_groups_route.py` (pages and routes), `tests/test_groups_schema.py` (tables, columns, safe to run twice)

Decision: `docs/decisions.md`, D15 (F16 in a reduced form; F18 fairness memory stays parked). Built after **A8** (home page list) is merged. Follows A7's way of changing the schema (D14): **new tables only, no new columns** in existing tables, so `init-db` adds everything to the deployed database by itself and no reviewed test that checks the columns of an existing table breaks.

## Why
A group of friends decides more than once. Today they need a new room, a new link and new nicknames every time. A fixed group keeps the members, so any member can start the next activity and everyone joins it with one tap, while guests from outside can still be invited to a single room.

## What

### Decisions in this spec (please check in the review)
- **The group id is the invite:** `secrets.token_urlsafe(8)` like room ids; the invite link is `/groups/<group_id>`. A separate invite token is not needed: the room id is also the room's invite.
- **Every member has the same rights:** start a new activity, see the invite link and QR code. The person who created the group is stored (`is_creator`) but has no extra rights in A9.
- **Membership is remembered like rooms:** `session["group_tokens"]`, a dict group id → member token, permanent cookie (A8), at most `MAX_REMEMBERED_GROUPS = 10`.
- **"Oldest remembered group" comes from the database, like in A8 (⚠ changed while writing the tests, please check in review):** Flask writes the session cookie with sorted keys, so the dict order is lost after every request. When an 11th group is remembered, the group where this browser's own `group_members.id` is smallest is dropped (ids only grow, so it is the group joined or created longest ago). A group joined last stays, even if it is older than all others.
- **A group room is a normal room** with a row in `group_rooms`. Everything else (options, voting, result) works unchanged.
- **One-tap join:** a group member who opens a group room they have not joined sees `Join as <group nickname>` instead of the nickname form. Taken by a guest already → the normal nickname form with the message below.
- **Whoever starts the activity becomes the room's creator** (start voting, close), as in F1, under their group nickname.
- **Guests:** a person who is not a member can join a group room with the room link and any free nickname, like today; they do not become group members.
- **Group nickname rules** are the same as room nicknames (A3): trimmed, 1–30 characters, unique within the group.
- **Group name:** trimmed, 1–60 characters.

### Schema (`app/schema.sql`, four new tables, no change to existing tables)
- `groups (id TEXT PRIMARY KEY, name TEXT NOT NULL CHECK (trim(name) <> ''), created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, last_activity_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)`
- `group_members (id INTEGER PRIMARY KEY, group_id TEXT NOT NULL REFERENCES groups (id) ON DELETE CASCADE, nickname TEXT NOT NULL CHECK (trim(nickname) <> ''), member_token TEXT NOT NULL UNIQUE, is_creator INTEGER NOT NULL DEFAULT 0 CHECK (is_creator IN (0, 1)), joined_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, UNIQUE (group_id, nickname))`
- `group_rooms (room_id TEXT PRIMARY KEY REFERENCES rooms (id) ON DELETE CASCADE, group_id TEXT NOT NULL REFERENCES groups (id) ON DELETE CASCADE)` – which room belongs to which group. Deleting the group removes only the link; the room stays until its own 7 days are over.
- `group_participants (participant_id INTEGER NOT NULL REFERENCES participants (id) ON DELETE CASCADE, group_member_id INTEGER NOT NULL REFERENCES group_members (id) ON DELETE CASCADE, PRIMARY KEY (participant_id))` – which room participant is which group member (one-tap join). Guests have no row. The primary key is written as a separate line on purpose: `schema_to_postgres` turns every `INTEGER PRIMARY KEY` into an identity column, which is wrong for a column that points at another table's id (review of PR #41).
- `rooms`, `participants` and every other existing table keep exactly their columns.
- `init-db` twice in a row changes nothing and deletes nothing; an existing database from before A9 gets the new tables with its data kept.

### Rules (`app/services/groups.py`, no Flask, no database)
- `validate_new_group(name, nickname) -> tuple[dict, list[str]]` – cleaned values and messages (`Please enter a group name.`, `The group name can be at most 60 characters.`, nickname messages as in A3).
- `join_group_errors(nickname, taken_nicknames) -> list[str]` – nickname messages as in A3, plus `This nickname is already taken in this group.`
- `remember_group_token(tokens, group_id, token) -> dict` – like A8's `remember_room_token`: a new dict with the group added or its token replaced.
- `groups_to_keep(groups) -> set[str]` – like A8's `rooms_to_keep`: takes groups with `id` and `member_id` (from `db.get_my_groups`) and returns the ids of the `MAX_REMEMBERED_GROUPS` groups with the highest `member_id`. The route trims `group_tokens` with it when there are more than 10.

### Routes (`app/routes/groups.py`, new blueprint; templates `group.html`, `new_group.html`)

| Method and path | Who | What |
|---|---|---|
| `GET /groups/new` | anyone | form: group name, your nickname |
| `POST /groups` | anyone | creates the group and its first member (`is_creator = 1`) in one transaction, remembers the token, redirects to the group page |
| `GET /groups/<id>` | member | name, members' nicknames, invite link and QR code (`_qr_code.html`), the group's rooms (newest first, status label and link as in A8), and the form "Plan a new activity" (title, mode) |
| `GET /groups/<id>` | not a member | group name and the join form (nickname); nothing else, no member names, no rooms |
| `POST /groups/<id>/join` | not a member | joins with a nickname, redirects to the group page; a member who posts again is redirected without a second member |
| `POST /groups/<id>/rooms` | member | creates a room, its `group_rooms` row, the member as room creator under their group nickname and their `group_participants` row, remembers the room token, updates `groups.last_activity_at`, redirects to the room page |

Rejected (message shown, nothing saved):

| Case | Status | Message |
|---|---|---|
| unknown group (any route) | 404 | – |
| `POST /groups` with invalid name or nickname | 400 | the rule messages, form shown again |
| join with an invalid or taken nickname | 400 | the rule messages |
| `POST /groups/<id>/rooms` by a non-member | 403 | `Please join the group before planning an activity.` |
| `POST /groups/<id>/rooms` with an invalid title or mode | 400 | the messages from F1 (`validate_new_room`), group page shown again |

### Changes to existing pages
- **Room page** (`GET /rooms/<id>`) of a group room for a visitor who is a member of that group: a form with one button `Join as <nickname>` posting to `POST /rooms/<id>/join` with the field `as_group_member=1`. The room page also shows `Part of <group name>` with a link to the group page, for participants whose browser is a member of that group (guests do not see it).
- **Join route**: with `as_group_member=1`, the nickname is taken from the group membership in the cookie (never from the form) and a `group_participants` row is stored in the same transaction as the participant. If the browser is not a member of the room's group, or the room belongs to no group at all: 403 `You are not a member of this group.`, nothing saved. If the nickname is already taken in the room: the normal nickname form with `Your group nickname is already taken in this room. Please choose another one.` (status 400). Joining without `as_group_member` works as before.
- **Home page** (A8): a section **"My groups"** above "My rooms" (name as a link to the group page, `<n> members`), from `group_tokens` (stale tokens dropped as in A8), and a link `Create a group` to `/groups/new`.

### `app/db.py`
Every function that writes uses `db.transaction()` and catches `db.INTEGRITY_ERRORS`, like `add_participant` and `save_vote`, and returns `False` when the database refuses (nothing saved).

New: `create_group_with_member(...) -> bool`, `get_group`, `get_group_member(group_id, member_token)`, `get_group_members(group_id)`, `add_group_member(group_id, nickname, member_token) -> bool` (`False` for a nickname taken a moment earlier, e.g. a double tap on "Join"; the route then shows `This nickname is already taken in this group.` with 400), `get_group_rooms(group_id)`, `create_group_room(...) -> bool` (one transaction: room, `group_rooms` row, creator participant, `group_participants` row, `last_activity_at`), `get_room_group(room_id)` (the group or `None`), `add_group_participant(room_id, nickname, session_token, group_member_id) -> bool` (participant and `group_participants` row in one transaction), `get_my_groups(tokens)` (each group with `id`, `name`, `member_count` and this browser's own `member_id`, which is only used by `groups_to_keep` and never shown). `add_participant` stays unchanged.

Checks (one line = one test):

`tests/test_groups_schema.py`
- [ ] A fresh database has `groups`, `group_members`, `group_rooms` and `group_participants` with the columns above, and `rooms` and `participants` have exactly the same columns as before A9.
- [ ] `init-db` on a database from before A9 adds the four tables and keeps every existing room, participant, option and vote; running it twice changes nothing.
- [ ] Two members with the same nickname in one group are refused by the database; the same nickname in two groups is fine.
- [ ] Deleting a group deletes its members, its `group_rooms` and `group_participants` rows; the rooms and their participants stay.
- [ ] Deleting a room deletes its `group_rooms` row; a room can belong to at most one group (primary key).
- [ ] A room participant has at most one `group_participants` row (primary key).
- [ ] Translated for Postgres, `group_participants` has no identity column, `group_members` has one.
- [ ] `init-db` twice in a row on a fresh database works.

`tests/test_groups.py`
- [ ] `validate_new_group` accepts a trimmed name and nickname; rejects empty, whitespace-only and too long values with the messages above.
- [ ] `join_group_errors` rejects a taken nickname (case as in A3) and invalid nicknames.
- [ ] `validate_new_group` accepts a 60-character name and a 30-character nickname.
- [ ] `remember_group_token` adds or replaces a token and does not change its input.
- [ ] `groups_to_keep` keeps the 10 groups with the highest member id; with 10 or fewer it keeps all.

`tests/test_groups_route.py`
- [ ] `GET /groups/new` shows the form with the fields `name` and `nickname`.
- [ ] Accepted: creating a group stores the group and one creator member, redirects to the group page, which shows the name, the creator's nickname, the invite link and the QR code.
- [ ] Accepted: a second browser opens the invite link, sees only the name and the join form, joins, and then sees both members.
- [ ] Accepted: a member plans an activity → a room with a `group_rooms` row, that member is the room's creator with their group nickname and a `group_participants` row, the browser is in the room, `last_activity_at` changes, and the group page lists the room with its status label.
- [ ] The group page lists the group's rooms newest first.
- [ ] Accepted: another member opens that room, sees `Join as <nickname>`, presses it and is a participant with the group nickname and a `group_participants` row, without typing anything; a nickname sent along in the form is ignored; the room page then shows `Part of <group name>`.
- [ ] Accepted: a guest (not a member) opens the room link, sees the normal nickname form, joins with any free nickname; they are not added to the group and do not see the group page.
- [ ] Accepted: the home page lists the browser's groups above its rooms; another browser sees none of them.
- [ ] Stale group token: a deleted group is not listed and its token is removed from the cookie.
- [ ] Joining an 11th group drops the oldest-remembered group; a group joined last stays even if it is older than all others.
- [ ] Rejected: invalid group name or nickname – 400, messages, nothing saved.
- [ ] Rejected: joining a group with a taken nickname – 400, message, nothing saved.
- [ ] Rejected: a non-member posts to `/groups/<id>/rooms` – 403, nothing saved.
- [ ] Rejected: planning an activity with an empty title or an unknown mode – 400, messages, nothing saved.
- [ ] Rejected: `as_group_member=1` from a browser that is not in the room's group – 403, nothing saved; a nickname sent in the form is ignored.
- [ ] Rejected: the group nickname is already taken in the room by a guest – 400, message, nickname form shown, nothing saved.
- [ ] Rejected: `as_group_member=1` on a room that belongs to no group – 403, `You are not a member of this group.`, nothing saved (no crash).
- [ ] Edge case: joining the same group twice from one browser does not create a second member.
- [ ] Edge case: pressing `Join as …` twice does not create a second participant.
- [ ] Edge case: `db.add_group_member` with a nickname that is already in the group returns `False` and saves nothing (two joins at the same moment).
- [ ] Edge case: if saving the `group_participants` row fails, no participant is saved either (one transaction).
- [ ] Edge case: unknown group id – 404 for every group route.
- [ ] Privacy: a non-member never sees member nicknames or the group's rooms; no page shows who voted what.
- [ ] Persistence: after an app restart, the group, its members and its rooms are still there and the browser is still a member.

## Out of scope
- F18 fairness weights, F17 history and "Been there" marks per group, the group map (C8).
- Renaming a group, removing or renaming members, leaving a group, admin rights, deleting a group by hand.
- The cleanup command (groups deleted 90 days after the last activity, D15).
- Notifying members about a new activity (no e-mail, no push); members see it on the group page.
- JavaScript, changes to existing tests.

## Done when
- All tests in the three test files and all earlier tests pass (`uv run pytest`), output pasted.
- The deployed database has the new tables without losing data (the A7 way), documented in the PR.
- On two phones: create a group, join it by QR code, plan two activities in a row; the second phone joins each with one tap.
- Work is on branch `feature-a9-groups`, pushed, pull request opened for review.
