"""Room page: invite link and QR code folded, "Delete this room" as a button (D21 follow-up after the phone test)."""

import re
from pathlib import Path

from typed_option import add_typed_option

APP_CSS = Path(__file__).resolve().parent.parent / "app" / "static" / "css" / "app.css"


def create_room(client):
    response = client.post("/rooms", data={"title": "Dinner", "mode": "manual", "nickname": "Anna"})
    assert response.status_code in (302, 303)
    room_id = response.headers["Location"].rsplit("/rooms/", 1)[1]
    add_typed_option(client, room_id, "Pizza")
    return room_id


def page(client, room_id):
    response = client.get(f"/rooms/{room_id}")
    assert response.status_code == 200
    return response.get_data(as_text=True)


def invite_fold(html):
    match = re.search(r'(<details\b[^>]*class="[^"]*\binvite-fold\b[^"]*"[^>]*>)(.*?)</details>', html, flags=re.DOTALL)
    assert match, "no <details class=\"invite-fold\">"
    return match.group(1), match.group(2)


def test_invite_link_and_qr_code_are_folded_for_everyone_in_the_room(app, client):
    room_id = create_room(client)
    guest = app.test_client()
    assert guest.post(f"/rooms/{room_id}/join", data={"nickname": "Ben"}).status_code in (302, 303)
    for browser in (client, guest):
        tag, inner = invite_fold(page(browser, room_id))
        assert " open" not in tag
        assert re.search(r"<summary[^>]*>\s*Invite friends\s*</summary>", inner)
        assert 'aria-label="Invite link"' in inner
        assert "Scan to join this room." in inner


def test_delete_this_room_is_a_button_for_the_creator_only(app, client):
    room_id = create_room(client)
    link = re.search(rf'<a\b([^>]*)href="/rooms/{room_id}/delete"([^>]*)>\s*Delete this room\s*</a>', page(client, room_id))
    assert link
    assert "danger-outline-button" in (link.group(1) + link.group(2))
    guest = app.test_client()
    guest.post(f"/rooms/{room_id}/join", data={"nickname": "Ben"})
    assert "Delete this room" not in page(guest, room_id)


def test_the_new_classes_are_styled():
    css = re.sub(r"/\*.*?\*/", "", APP_CSS.read_text(), flags=re.DOTALL)
    assert re.search(r"\.invite-fold\b[^{]*\{", css)
    assert re.search(r"\.danger-outline-button\b[^{]*\{", css)
