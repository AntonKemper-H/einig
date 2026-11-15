"""Room pages: create a room (F1), show and join it (F2), add options (F3), lobby and start voting (F7)."""

from flask import Blueprint, abort, redirect, render_template, request, session, url_for

from app import db
from app.services import lobby as lobby_rules
from app.services import options as option_rules
from app.services import rooms as room_rules

bp = Blueprint("rooms", __name__)

CREATE_COLLISION_MESSAGE = "Something went wrong while creating the room. Please try again."
JOIN_COLLISION_MESSAGE = "Something went wrong while joining. Please try again."
NOT_JOINED_MESSAGE = "Please join the room before adding options."
OPTION_REFUSED_MESSAGE = "Something went wrong while adding the option. Please try again."
ONLY_CREATOR_MESSAGE = "Only the creator can start the voting."


def session_token_for(room_id: str) -> str | None:
    """Return the token this browser stored for the room, or None."""
    return session.get("participant_tokens", {}).get(room_id)


def remember_token(room_id: str, session_token: str) -> None:
    """Store the participant's token in the signed session cookie, next to tokens for other rooms."""
    # A new dict is assigned so Flask notices the change and saves the cookie.
    tokens = dict(session.get("participant_tokens", {}))
    tokens[room_id] = session_token
    session["participant_tokens"] = tokens


def render_room_page(
    room,
    participant,
    join_nickname: str = "",
    errors: list[str] | None = None,
    option_label: str = "",
    option_errors: list[str] | None = None,
):
    """Render the room page: join form for visitors; options and add form for participants."""
    invite_url = url_for("rooms.show_room", room_id=room["id"], _external=True)
    # Only participants may see the options, so visitors get an empty list.
    options = db.get_options(room["id"]) if participant else []
    return render_template(
        "room.html",
        room=room,
        participant=participant,
        invite_url=invite_url,
        join_nickname=join_nickname,
        errors=errors or [],
        options=options,
        option_label=option_label,
        option_errors=option_errors or [],
    )


def render_lobby(room, participant, errors: list[str] | None = None):
    """Render the lobby: who has joined, who is done, the room status and the creator's start button."""
    participants = db.get_participants(room["id"])
    finished_count = sum(1 for person in participants if person["has_finished"])
    option_count = len(db.get_options(room["id"]))
    # The creator sees why "Start voting" would be rejected, on the normal lobby
    # page, so the hint survives the refresh. Skipped when an error is already shown.
    start_hints = []
    if participant["is_creator"] and room["status"] == "collecting" and not errors:
        start_hints = lobby_rules.start_errors(room["status"], option_count)
    return render_template(
        "lobby.html",
        room=room,
        participant=participant,
        participants=participants,
        finished_count=finished_count,
        option_count=option_count,
        start_hints=start_hints,
        status_text=lobby_rules.status_text(room["status"]),
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


@bp.post("/rooms/<room_id>/options")
def add_option(room_id: str):
    """F3: a participant adds an option while the room is collecting, then redirect (Post/Redirect/Get)."""
    room = db.get_room(room_id)
    if room is None:
        abort(404)

    # Permission check on the server: hiding the form is not enough.
    participant = db.get_participant(room_id, session_token_for(room_id))
    if participant is None:
        return render_room_page(room, None, errors=[NOT_JOINED_MESSAGE]), 403

    label = room_rules.clean_text(request.form.get("label"))
    errors = option_rules.option_errors(label, room["status"], db.get_option_labels(room_id))
    if errors:
        return render_room_page(room, participant, option_label=label, option_errors=errors), 400

    if not db.add_manual_option(room_id, label):
        return render_room_page(
            room, participant, option_label=label, option_errors=[OPTION_REFUSED_MESSAGE]
        ), 400

    return redirect(url_for("rooms.show_room", room_id=room_id), code=303)


@bp.get("/rooms/<room_id>/lobby")
def show_lobby(room_id: str):
    """F7: the lobby page, which reloads itself every few seconds (meta refresh in the template)."""
    room = db.get_room(room_id)
    if room is None:
        abort(404)
    participant = db.get_participant(room_id, session_token_for(room_id))
    if participant is None:
        # Visitors join first; the join form is on the room page.
        return redirect(url_for("rooms.show_room", room_id=room_id), code=303)
    return render_lobby(room, participant)


@bp.post("/rooms/<room_id>/start")
def start_voting(room_id: str):
    """The creator ends the collecting phase and starts the voting, then redirect (Post/Redirect/Get)."""
    room = db.get_room(room_id)
    if room is None:
        abort(404)

    # Creator-only action, checked on the server: hiding the button is not enough.
    participant = db.get_participant(room_id, session_token_for(room_id))
    if participant is None:
        return render_room_page(room, None, errors=[ONLY_CREATOR_MESSAGE]), 403
    if not participant["is_creator"]:
        return render_lobby(room, participant, [ONLY_CREATOR_MESSAGE]), 403

    errors = lobby_rules.start_errors(room["status"], len(db.get_options(room_id)))
    if errors:
        return render_lobby(room, participant, errors), 400

    if not db.start_voting(room_id):
        # Someone else started it a moment earlier.
        return render_lobby(room, participant, [lobby_rules.ALREADY_STARTED_MESSAGE]), 400

    return redirect(url_for("rooms.show_lobby", room_id=room_id), code=303)
