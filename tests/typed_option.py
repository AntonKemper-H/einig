"""Test helper: put a typed option into a room as a participant (specs/e1-places-only-via-maps.md).

The page has no form for typed options any more, but older rooms still contain them
and many tests need some options to work with. This saves one directly, like the
old route did: the option and its author together.
"""

from types import SimpleNamespace

from app import db


def add_typed_option(client, room_id, label):
    """Save a typed option for the participant behind this client. Return a 303-like response."""
    with client.session_transaction() as session:
        token = session["participant_tokens"][room_id]
    with client.application.app_context():
        participant = db.get_participant(room_id, token)
        with db.transaction() as connection:
            option = connection.execute(
                "INSERT INTO options (room_id, source, label) VALUES (?, 'manual', ?) RETURNING id",
                (room_id, label),
            ).fetchone()
            connection.execute(
                "INSERT INTO option_authors (option_id, room_id, participant_id) VALUES (?, ?, ?)",
                (option["id"], room_id, participant["id"]),
            )
    return SimpleNamespace(status_code=303, headers={"Location": f"/rooms/{room_id}"})
