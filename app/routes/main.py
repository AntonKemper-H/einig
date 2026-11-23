"""General pages: home page and health check."""

from flask import Blueprint, render_template, session, url_for

from app import db
from app.services import activities
from app.services import rooms as room_rules

bp = Blueprint("main", __name__)


@bp.get("/")
def home():
    """Home page: "My groups" (F16), "My rooms" (F25) and the "create a room" form (F1)."""
    return render_home({}, [])


def render_home(form: dict, errors: list[str]) -> str:
    """The home page; also used by rooms.create_room to show the form again with errors."""
    return render_template(
        "home.html",
        form=form,
        errors=errors,
        modes=room_rules.MODES,
        kind_choices=activities.kind_choices(),
        my_groups=load_my_groups(),
        my_rooms=load_my_rooms(),
    )


def load_my_rooms() -> list[dict]:
    """The rooms this browser is in (A8), each with its link and status label.

    Tokens of deleted rooms, and tokens that belong to no participant of their room,
    are removed from the cookie here.
    """
    tokens = session.get("participant_tokens", {})
    my_rooms = db.get_my_rooms(tokens)
    found_ids = {room["id"] for room in my_rooms}
    if found_ids != set(tokens):
        session["participant_tokens"] = {
            room_id: token for room_id, token in tokens.items() if room_id in found_ids
        }
    for room in my_rooms:
        room["url"] = url_for(room_rules.room_link_endpoint(room["status"]), room_id=room["id"])
        room["status_label"] = room_rules.STATUS_LABELS.get(room["status"], room["status"])
    return my_rooms


@bp.get("/health")
def health():
    """Plain 'ok' so the hosting service can check that the app is running."""
    return "ok", 200, {"Content-Type": "text/plain; charset=utf-8"}


def load_my_groups() -> list[dict]:
    """The groups this browser is a member of (A9); tokens of deleted groups are removed."""
    tokens = session.get("group_tokens", {})
    my_groups = db.get_my_groups(tokens)
    found_ids = {group["id"] for group in my_groups}
    if found_ids != set(tokens):
        session["group_tokens"] = {
            group_id: token for group_id, token in tokens.items() if group_id in found_ids
        }
    return my_groups
