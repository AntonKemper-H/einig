-- Table definitions for Einig.
-- Tables for rooms, participants, options and votes are added in Sprint 1 (F1–F3)
-- by the schema owner. See the data model in docs/concept.md, section 7.

-- Small placeholder so init-db creates a real database file.
DROP TABLE IF EXISTS app_info;
CREATE TABLE app_info (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
INSERT INTO app_info (key, value) VALUES ('schema_version', '0');
