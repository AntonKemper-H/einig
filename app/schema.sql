-- Table definitions for Einig.
-- Tables for rooms, participants, options and votes are added in Sprint 1 (F1–F3)
-- by the schema owner. See the data model in docs/concept.md, section 7.
--
-- This file must never delete data: it only creates what is missing
-- ("IF NOT EXISTS", "INSERT OR IGNORE"). Deleting everything is the job of
-- the separate reset-db command, which asks for confirmation first.

-- Small placeholder so init-db creates a real database file.
CREATE TABLE IF NOT EXISTS app_info (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
INSERT OR IGNORE INTO app_info (key, value) VALUES ('schema_version', '0');
