# E1 – Places only via Google Maps

Branch: `fix-places-only-via-maps`
Tests: `tests/test_places_only_via_maps.py` (new). Older tests that used the typed-option form as a set-up shortcut now insert the option directly (`tests/conftest.py`, `seed_typed_option`); tests of the removed form are deleted.

## Why
A place typed in by hand has no Google Maps data, so its card has no photo, rating or map. Every place should therefore come from Google Maps.

## What
- The room page has **no "Add an option" text field** any more, in every room mode (also "Enter options myself" and the collapsed "Add your own idea" row).
- `POST /rooms/<id>/options` no longer exists (404/405); nothing is saved.
- In a manual room the way to add a place is "Find a place on Google Maps" (F23, C6). Its messages no longer offer "add it as your own option".
- The find form is shown whenever a place can be added (collecting, below the options limit).
- Old rooms keep their typed options: they are still shown, voted on, and deletable.
- Dead code removed: `db.add_manual_option`, `db.add_manual_option_within_limit`, `db.get_option_labels`, `options.option_errors`, `is_someone_elses_hidden_idea`.
