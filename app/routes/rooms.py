"""Room pages: create a room and show it (more room actions follow in A3–A5)."""

from flask import Blueprint, abort, redirect, render_template, request, session, url_for

from app import db
from app.services import rooms as room_rules

bp = Blueprint("rooms", __name__)

COLLISION_MESSAGE = "Something went wrong while creating the room. Please try again."


def show_form_again(form: dict, errors: list[str]):
    """Show the create-room form with the entered values and the error messages (status 400)."""
    return render_template("home.html", form=form, errors=errors, modes=room_rules.MODES), 400


@bp.post("/rooms")
def create_room():
    """F1: check the form, save the room and its creator, then redirect (Post/Redirect/Get)."""
    form, errors = room_rules.validate_new_room(
        request.form.get("title"), request.form.get("mode"), request.form.get("nickname")
    )
    if errors:
        return show_form_again(form, errors)

    room_id = room_rules.new_room_id()
    session_token = room_rules.new_session_token()
    saved = db.create_room_with_creator(
        room_id, form["title"], form["mode"], form["nickname"], session_token
    )
    if not saved:
        return show_form_again(form, [COLLISION_MESSAGE])

    # Remember the creator in the signed session cookie, one token per room.
    # A new dict is assigned so Flask notices the change and saves the cookie.
    tokens = dict(session.get("participant_tokens", {}))
    tokens[room_id] = session_token
    session["participant_tokens"] = tokens

    return redirect(url_for("rooms.show_room", room_id=room_id), code=303)


@bp.get("/rooms/<room_id>")
def show_room(room_id: str):
    """Minimal room page: title and invite link. The lobby follows in A5."""
    room = db.get_room(room_id)
    if room is None:
        abort(404)
    invite_url = url_for("rooms.show_room", room_id=room_id, _external=True)
    return render_template("room.html", room=room, invite_url=invite_url)
