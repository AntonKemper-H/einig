-- Table definitions for Einig (spec: specs/a1-schema.md).
-- Based on the data model in docs/concept.md, section 7, reduced to F1–F13 + F22.
--
-- This file must never delete data: it only creates what is missing
-- ("IF NOT EXISTS", "INSERT OR IGNORE"). Deleting everything is the job of
-- the separate reset-db command, which asks for confirmation first.
--
-- The rules for simultaneous actions (AGENTS.md) are enforced here with
-- UNIQUE constraints, so two requests at the same moment can never both win.

-- Small placeholder so init-db creates a real database file.
CREATE TABLE IF NOT EXISTS app_info (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
INSERT OR IGNORE INTO app_info (key, value) VALUES ('schema_version', '1');
-- Older databases still say '0'. Updating one value deletes nothing.
-- Note: CREATE TABLE IF NOT EXISTS never changes an existing table, so new
-- CHECK rules only reach an old database after reset-db (decided in C1).
UPDATE app_info SET value = '1' WHERE key = 'schema_version';


-- One decision. The id is a random token from the app, never a counter.
CREATE TABLE IF NOT EXISTS rooms (
    id                TEXT PRIMARY KEY,
    title             TEXT NOT NULL CHECK (trim(title) <> ''),
    mode              TEXT NOT NULL CHECK (mode IN ('manual', 'nearby', 'surprise')),
    status            TEXT NOT NULL DEFAULT 'collecting'
                      CHECK (status IN ('collecting', 'voting', 'closed')),
    -- All times are UTC text 'YYYY-MM-DD HH:MM:SS' (the CURRENT_TIMESTAMP format),
    -- so they compare correctly as text.
    deadline          TEXT,      -- optional (F11)
    search_center_lat REAL CHECK (search_center_lat BETWEEN -90 AND 90),   -- optional, rounded (F8, F12)
    search_center_lng REAL CHECK (search_center_lng BETWEEN -180 AND 180),
    radius_m          INTEGER CHECK (radius_m > 0),
    filters           TEXT,      -- optional JSON: category, price level, minimum rating ...
    -- Stored when the room closes, so closing again returns the same winner.
    -- No foreign key: rooms and options would point at each other, which
    -- Postgres cannot create in one pass. The app only stores an option of this room.
    winner_option_id  INTEGER,
    created_at        TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);


-- One person in one room. No accounts: the session token identifies them.
CREATE TABLE IF NOT EXISTS participants (
    id            INTEGER PRIMARY KEY,
    room_id       TEXT NOT NULL REFERENCES rooms (id) ON DELETE CASCADE,
    nickname      TEXT NOT NULL CHECK (trim(nickname) <> ''),
    session_token TEXT NOT NULL UNIQUE,
    is_creator    INTEGER NOT NULL DEFAULT 0 CHECK (is_creator IN (0, 1)),
    has_finished  INTEGER NOT NULL DEFAULT 0 CHECK (has_finished IN (0, 1)),
    UNIQUE (room_id, nickname),
    -- Lets votes and vetoes check that a participant belongs to their room.
    UNIQUE (id, room_id)
);


-- One thing to choose. A Google option stores only its place_id (Google terms);
-- name, photo and rating are loaded fresh when shown.
CREATE TABLE IF NOT EXISTS options (
    id          INTEGER PRIMARY KEY,
    room_id     TEXT NOT NULL REFERENCES rooms (id) ON DELETE CASCADE,
    source      TEXT NOT NULL CHECK (source IN ('manual', 'google')),
    label       TEXT,
    place_id    TEXT,
    category    TEXT,      -- optional sub-category, so surprise mode can mix (F12)
    is_replaced INTEGER NOT NULL DEFAULT 0 CHECK (is_replaced IN (0, 1)),  -- "Been there" (F13)
    -- Exactly one of label / place_id is filled, depending on the source.
    CHECK (
        (source = 'manual' AND label IS NOT NULL AND trim(label) <> '' AND place_id IS NULL)
        OR (source = 'google' AND place_id IS NOT NULL AND trim(place_id) <> '' AND label IS NULL)
    ),
    UNIQUE (room_id, label),
    UNIQUE (room_id, place_id),
    -- Lets votes and vetoes check that an option belongs to their room.
    UNIQUE (id, room_id)
);


-- One rating. At most one per participant and option; voting again replaces it.
CREATE TABLE IF NOT EXISTS votes (
    id             INTEGER PRIMARY KEY,
    room_id        TEXT NOT NULL,
    participant_id INTEGER NOT NULL,
    option_id      INTEGER NOT NULL,
    rating         TEXT NOT NULL CHECK (rating IN ('yes', 'ok', 'no')),
    UNIQUE (participant_id, option_id),
    -- Both foreign keys include room_id, so participant and option must be in the same room.
    FOREIGN KEY (participant_id, room_id) REFERENCES participants (id, room_id) ON DELETE CASCADE,
    FOREIGN KEY (option_id, room_id) REFERENCES options (id, room_id) ON DELETE CASCADE
);


-- The joker. At most one per participant and room.
CREATE TABLE IF NOT EXISTS vetoes (
    id             INTEGER PRIMARY KEY,
    room_id        TEXT NOT NULL,
    participant_id INTEGER NOT NULL,
    option_id      INTEGER NOT NULL,
    UNIQUE (participant_id, room_id),
    FOREIGN KEY (participant_id, room_id) REFERENCES participants (id, room_id) ON DELETE CASCADE,
    FOREIGN KEY (option_id, room_id) REFERENCES options (id, room_id) ON DELETE CASCADE
);


-- Who added a manual option, for the delete permission (F24, specs/a7-delete-option.md).
-- A table of its own instead of a column on options: init-db adds it to an existing
-- database by itself, and the columns of options stay as they are (C5's test checks them).
-- Options from the nearby/surprise search have no row: only the creator may delete those.
-- Never shown to anyone; only used for the permission check.
CREATE TABLE IF NOT EXISTS option_authors (
    option_id      INTEGER NOT NULL,
    room_id        TEXT NOT NULL,
    participant_id INTEGER NOT NULL,
    PRIMARY KEY (option_id),
    -- Both foreign keys include room_id, so the author is always in the option's room.
    FOREIGN KEY (option_id, room_id) REFERENCES options (id, room_id) ON DELETE CASCADE,
    FOREIGN KEY (participant_id, room_id) REFERENCES participants (id, room_id) ON DELETE CASCADE
);

-- The room setup (F27, specs/c9-room-setup.md, D17): what the group is planning and
-- how many options each person may add. A table of its own, so init-db adds it to an
-- existing database. A room without a row works as before (no kind, no limit).
CREATE TABLE IF NOT EXISTS room_setups (
    room_id            TEXT PRIMARY KEY REFERENCES rooms (id) ON DELETE CASCADE,
    activity           TEXT NOT NULL CHECK (trim(activity) <> ''),
    kind               TEXT NOT NULL CHECK (trim(kind) <> ''),
    -- NULL means unlimited.
    options_per_person INTEGER CHECK (options_per_person BETWEEN 1 AND 5),
    -- Used by A11 (F28, hidden collecting); C9 only creates them with today's behaviour.
    hide_ideas         INTEGER NOT NULL DEFAULT 0 CHECK (hide_ideas IN (0, 1)),
    reveal_places      INTEGER NOT NULL DEFAULT 1 CHECK (reveal_places IN (0, 1))
);
