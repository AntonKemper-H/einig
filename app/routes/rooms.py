"""Room pages: create a room (F1), show it and join it (F2). The lobby follows in A5."""

from flask import Blueprint, abort, redirect, render_template, request, session, url_for

from app import db
from app.services import rooms as room_rules

bp = Blueprint("rooms", __name__)

CREATE_COLLISION_MESSAGE = "Something went wrong while creating the room. Please try again."
JOIN_COLLISION_MESSAGE = "Something went wrong while joining. Please try again."


def session_token_for(room_id: str) -> str | None:
    """Return the token this browser stored for the room, or None."""
    return session.get("participant_tokens", {}).get(room_id)


def remember_token(room_id: str, session_token: str) -> None:
    """Store the participant's token in the signed session cookie, next to tokens for other rooms."""
    # A new dict is assigned so Flask notices the change and saves the cookie.
    tokens = dict(session.get("participant_tokens", {}))
    tokens[room_id] = session_token
    session["participant_tokens"] = tokens


def render_room_page(room, participant, join_nickname: str = "", errors: list[str] | None = None):
    """Render the room page: join form for visitors, 'you joined' for participants."""
    invite_url = url_for("rooms.show_room", room_id=room["id"], _external=True)
    return render_template(
        "room.html",
        room=room,
        participant=participant,
        invite_url=invite_url,
        join_nickname=join_nickname,
        errors=errors or [],
    )


def show_create_form_again(form: dict, errors: list[str]):
    """Show the create-room form with the entered values and the error messages (status 400)."""
    return render_template("home.html", form=form, errors=errors, modes=room_rules.MODES), 400


@bp.post("/rooms")
def create_room():
    """F1: check the form, save the room and its creator, then redirect (Post/Redirect/Get)."""
    form, errors = room_rules.validate_new_room(
        request.form.get("title"), request.form.get("mode"), request.form.get("nickname")
    )
    if errors:
        return show_create_form_again(form, errors)

    room_id = room_rules.new_room_id()
    session_token = room_rules.new_session_token()
    saved = db.create_room_with_creator(
        room_id, form["title"], form["mode"], form["nickname"], session_token
    )
    if not saved:
        return show_create_form_again(form, [CREATE_COLLISION_MESSAGE])

    remember_token(room_id, session_token)
    return redirect(url_for("rooms.show_room", room_id=room_id), code=303)


@bp.get("/rooms/<room_id>")
def show_room(room_id: str):
    """Room page and invite link target: participants see who they are, visitors see the join form."""
    room = db.get_room(room_id)
    if room is None:
        abort(404)
    participant = db.get_participant(room_id, session_token_for(room_id))
    return render_room_page(room, participant)


@bp.post("/rooms/<room_id>/join")
def join_room(room_id: str):
    """F2: join a room with a nickname, no account needed, then redirect (Post/Redirect/Get)."""
    room = db.get_room(room_id)
    if room is None:
        abort(404)

    # Already in this room (e.g. "Join" pressed twice): never create a second participant.
    if db.get_participant(room_id, session_token_for(room_id)) is not None:
        return redirect(url_for("rooms.show_room", room_id=room_id), code=303)

    nickname = room_rules.clean_text(request.form.get("nickname"))
    errors = room_rules.join_errors(
        nickname, room["status"], db.get_nicknames(room_id)
    )
    if errors:
        return render_room_page(room, None, nickname, errors), 400

    session_token = room_rules.new_session_token()
    if not db.add_participant(room_id, nickname, session_token):
        return render_room_page(room, None, nickname, [JOIN_COLLISION_MESSAGE]), 400

    remember_token(room_id, session_token)
    return redirect(url_for("rooms.show_room", room_id=room_id), code=303)
