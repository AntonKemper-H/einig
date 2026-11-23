"""Tests for U3 – invite in one tap, and groups first (specs/u3-invite-groups.md)."""

import re
from pathlib import Path
from urllib.parse import quote

from app.db import get_db

ROOT = Path(__file__).resolve().parent.parent
INVITE_JS = ROOT / "app" / "static" / "js" / "invite.js"
CSS = ROOT / "app" / "static" / "css" / "app.css"


def create_room(client, title="Dinner on Friday"):
    response = client.post("/rooms", data={"title": title, "mode": "manual", "nickname": "Anna"})
    return response.headers["Location"].rsplit("/rooms/", 1)[1]


def create_group(client, name="Friday friends"):
    response = client.post("/groups", data={"name": name, "nickname": "Anna"})
    return response.headers["Location"].rsplit("/groups/", 1)[1]


def page(client, path):
    response = client.get(path)
    assert response.status_code == 200
    return response.get_data(as_text=True)


def invite_block(html):
    match = re.search(r'<div class="invite-actions".*?</div>', html, flags=re.DOTALL)
    return match.group(0) if match else None


def test_a_participant_gets_the_invite_button_and_the_three_links(client):
    room_id = create_room(client)
    html = page(client, f"/rooms/{room_id}")
    block = invite_block(html)
    assert block
    invite_url = f"http://localhost/rooms/{room_id}"
    assert re.search(r'<button[^>]*id="invite-button"[^>]*hidden[^>]*>\s*Invite\s*</button>', block)
    # Percent-encoded, so the raw link is not on the page twice more (reviewed layout test); invite.js decodes it.
    assert f'data-url="{quote(invite_url, safe="")}"' in block
    text = quote(f'Join "Dinner on Friday" on Einig: {invite_url}', safe="")
    assert f'href="whatsapp://send?text={text}"' in block
    assert 'href="mailto:?subject=' in block and text in block
    assert f'href="sms:?&amp;body={text}"' in block or f'href="sms:?&body={text}"' in block
    # The folded link and QR code stay (reviewed test: invite_urls_in in tests/test_proxy_headers.py).
    assert 'aria-label="Invite link"' in html


def test_a_visitor_and_a_closed_room_show_no_invite_block(app, client):
    room_id = create_room(client)
    assert invite_block(page(app.test_client(), f"/rooms/{room_id}")) is None
    with app.app_context():
        db = get_db()
        db.execute("UPDATE rooms SET status = 'closed' WHERE id = ?", (room_id,))
        db.commit()
    assert invite_block(page(client, f"/rooms/{room_id}")) is None


def test_a_group_member_gets_the_invite_block_and_others_do_not(app, client):
    group_id = create_group(client)
    block = invite_block(page(client, f"/groups/{group_id}"))
    assert block
    assert f'data-url="{quote(f"http://localhost/groups/{group_id}", safe="")}"' in block
    assert quote("Friday friends", safe="") in block
    assert invite_block(page(app.test_client(), f"/groups/{group_id}")) is None


def test_the_invite_message_holds_no_nickname(client):
    room_id = create_room(client)
    block = invite_block(page(client, f"/rooms/{room_id}"))
    assert "Anna" not in block


def test_invite_js_is_small_loaded_by_both_pages_and_the_only_new_script(client):
    source = INVITE_JS.read_text()
    assert "navigator.share" in source
    assert len(source.splitlines()) <= 30
    room_id = create_room(client)
    group_id = create_group(client)
    for path in (f"/rooms/{room_id}", f"/groups/{group_id}"):
        assert "js/invite.js" in page(client, path)
    names = {path.name for path in INVITE_JS.parent.glob("*.js")}
    assert names == {"geolocation.js", "swipe.js", "invite.js"}


def test_a_group_tile_has_a_new_decision_link_to_the_plan_form(client):
    group_id = create_group(client)
    html = page(client, "/")
    assert re.search(rf'<a[^>]*href="/groups/{group_id}#plan"[^>]*>\s*New decision\s*</a>', html)
    assert 'id="plan"' in page(client, f"/groups/{group_id}")


def test_the_stylesheet_puts_the_groups_first_and_the_html_order_stays(client):
    assert re.search(r"\.home-groups\s*\{[^}]*order:\s*0", CSS.read_text())
    html = page(client, "/")
    assert html.index("home-groups") < html.index("home-rooms") < html.index("home-create")
