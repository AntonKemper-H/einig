"""Room pages: create a room (F1), show and join it (F2), add and delete options (F3, F24),
lobby and start voting (F7), suggest places nearby (F8), surprise mode (F12),
"Been there" (F13), rating (F4), close the room and show the result (F6)."""

import random

from flask import (
    Blueprint,
    abort,
    current_app,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from app import db
from app.routes.main import render_home
from app.services import lobby as lobby_rules
from app.services import options as option_rules
from app.services import places, qr, surprise
from app.services import results as result_rules
from app.services import rooms as room_rules
from app.services import voting as voting_rules
from app.services.scoring import pick_winner

bp = Blueprint("rooms", __name__)

CREATE_COLLISION_MESSAGE = "Something went wrong while creating the room. Please try again."
JOIN_COLLISION_MESSAGE = "Something went wrong while joining. Please try again."
NOT_JOINED_MESSAGE = "Please join the room before adding options."
NOT_JOINED_DELETE_MESSAGE = "Please join the room before deleting options."
OPTION_REFUSED_MESSAGE = "Something went wrong while adding the option. Please try again."
ONLY_CREATOR_MESSAGE = "Only the creator can start the voting."
PLACES_UNAVAILABLE_MESSAGE = (
    "Place suggestions are not available right now. You can still add options yourself."
)
NO_PLACES_FOUND_MESSAGE = "No places found. Try a larger radius or fewer filters."
NOT_JOINED_VOTE_MESSAGE = "Please join the room before voting."
VOTE_REFUSED_MESSAGE = "Something went wrong while saving your rating. Please try again."
GOOGLE_OPTION_LABEL = "Place from Google Maps"


def session_token_for(room_id: str) -> str | None:
    """Return the token this browser stored for the room, or None."""
    return session.get("participant_tokens", {}).get(room_id)


def remember_token(room_id: str, session_token: str) -> None:
    """Store the participant's token in the signed session cookie, next to tokens for other rooms.

    The cookie lasts 180 days (A8). With more than 30 rooms, the room this browser
    joined longest ago is forgotten, so the cookie never grows too big for the browser.
    """
    tokens = room_rules.remember_room_token(
        session.get("participant_tokens", {}), room_id, session_token
    )
    if len(tokens) > room_rules.MAX_REMEMBERED_ROOMS:
        # Called after the participant is saved, so the new room counts as the newest.
        keep = room_rules.rooms_to_keep(db.get_my_rooms(tokens))
        tokens = {key: token for key, token in tokens.items() if key in keep}
    # A new dict is assigned so Flask notices the change and saves the cookie.
    session["participant_tokens"] = tokens
    session.permanent = True


def invite_url_for(room_id: str) -> str:
    """The full link friends open to join (A2); also what the QR code holds (A6)."""
    return url_for("rooms.show_room", room_id=room_id, _external=True)


def render_room_page(
    room,
    participant,
    join_nickname: str = "",
    errors: list[str] | None = None,
    option_label: str = "",
    option_errors: list[str] | None = None,
    search_values=None,
    search_errors: list[str] | None = None,
    been_there_errors: list[str] | None = None,
):
    """Render the room page: join form for visitors; options, add form and place search for participants."""
    invite_url = invite_url_for(room["id"])
    # Only participants may see the options, so visitors get an empty list
    # (and their page view never calls Google).
    options = db.get_options(room["id"]) if participant else []
    # Google details are loaded fresh for every view: Google only allows storing the place id.
    cards = places.load_cards(
        current_app.config.get("GOOGLE_MAPS_API_KEY"),
        options,
        room["search_center_lat"],
        room["search_center_lng"],
    )
    # The search form uses the same rules as the route, so it is shown exactly when a search is allowed.
    show_search_form = False
    show_surprise_form = False
    if participant is not None:
        already_suggested = db.has_google_options(room["id"])
        show_search_form = places.search_refusal(
            bool(participant["is_creator"]), room["mode"], room["status"], already_suggested
        ) is None
        show_surprise_form = surprise.surprise_refusal(
            bool(participant["is_creator"]), room["mode"], room["status"], already_suggested
        ) is None
    # F12: tell the group if the surprise search had to widen the radius (participants only).
    widened_to = None
    if participant is not None:
        widened_to = surprise.widened_to_text(room["mode"], room["radius_m"], room["filters"])
    # F13: the ids of the options whose card gets a "Been there" button.
    been_there_ids = {
        option["id"]
        for option in options
        if surprise.can_press_been_there(room["mode"], room["status"], option["source"])
    }
    # F24: the options whose card gets a "Delete" button (only while collecting).
    deletable_ids = set()
    if participant is not None and room["status"] == "collecting":
        deletable_ids = {
            option["id"]
            for option in options
            if option_rules.may_delete(
                bool(participant["is_creator"]), participant["id"], option["added_by"]
            )
        }
    return render_template(
        "room.html",
        room=room,
        participant=participant,
        invite_url=invite_url,
        qr_svg=qr.invite_qr_svg(invite_url),
        join_nickname=join_nickname,
        errors=errors or [],
        cards=cards,
        option_label=option_label,
        option_errors=option_errors or [],
        show_search_form=show_search_form,
        show_surprise_form=show_surprise_form,
        surprise_categories=surprise.CATEGORY_LABELS,
        widened_to=widened_to,
        option_ids=[option["id"] for option in options],
        been_there_ids=been_there_ids,
        deletable_ids=deletable_ids,
        been_there_errors=been_there_errors or [],
        search_values=search_values or {},
        search_errors=search_errors or [],
        categories=places.CATEGORIES,
        radius_choices=places.RADIUS_CHOICES,
        min_rating_choices=places.MIN_RATING_CHOICES,
        price_level_choices=places.PRICE_LEVEL_CHOICES,
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
        qr_svg=qr.invite_qr_svg(invite_url_for(room["id"])),
        status_text=lobby_rules.status_text(room["status"]),
        errors=errors or [],
    )


def show_create_form_again(form: dict, errors: list[str]):
    """Show the create-room form with the entered values and the error messages (status 400)."""
    return render_home(form, errors), 400


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

    if not db.add_manual_option(room_id, label, participant["id"]):
        return render_room_page(
            room, participant, option_label=label, option_errors=[OPTION_REFUSED_MESSAGE]
        ), 400

    return redirect(url_for("rooms.show_room", room_id=room_id), code=303)


@bp.post("/rooms/<room_id>/options/<int:option_id>/delete")
def delete_option(room_id: str, option_id: int):
    """F24: the author or the creator deletes an option while collecting (Post/Redirect/Get)."""
    room = db.get_room(room_id)
    if room is None:
        abort(404)

    # Permission check on the server: hiding the button is not enough.
    participant = db.get_participant(room_id, session_token_for(room_id))
    if participant is None:
        return render_room_page(room, None, errors=[NOT_JOINED_DELETE_MESSAGE]), 403

    room_page = redirect(url_for("rooms.show_room", room_id=room_id), code=303)

    option = db.get_option(room_id, option_id)
    if option is None or option["is_replaced"]:
        # Already gone, replaced, or not an option of this room: AGENTS.md says it changes nothing.
        return room_page

    error = option_rules.delete_error(
        room["status"], bool(participant["is_creator"]), participant["id"], option["added_by"]
    )
    if error is not None:
        message, status_code = error
        return render_room_page(room, participant, option_errors=[message]), status_code

    if not db.delete_option(room_id, option_id):
        # Another request was first. If the option is still there, the voting has started.
        option = db.get_option(room_id, option_id)
        if option is not None and not option["is_replaced"]:
            return render_room_page(
                room, participant, option_errors=[option_rules.DELETE_NOT_COLLECTING_MESSAGE]
            ), 400

    return room_page


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


@bp.post("/rooms/<room_id>/suggest")
def suggest_places(room_id: str):
    """F8: the creator searches places nearby once; they are saved as options (Post/Redirect/Get)."""
    room = db.get_room(room_id)
    if room is None:
        abort(404)

    # Permission check on the server: hiding the form is not enough.
    participant = db.get_participant(room_id, session_token_for(room_id))
    if participant is None:
        return render_room_page(room, None, errors=[NOT_JOINED_MESSAGE]), 403

    refusal = places.search_refusal(
        bool(participant["is_creator"]),
        room["mode"],
        room["status"],
        db.has_google_options(room_id),
    )
    if refusal is not None:
        status_code, message = refusal
        return render_room_page(room, participant, search_errors=[message]), status_code

    def show_search_again(messages: list[str], status_code: int):
        """The room page with the entered search values and the messages."""
        return render_room_page(
            room,
            participant,
            search_values=places.values_to_show_again(request.form),
            search_errors=messages,
        ), status_code

    search, errors = places.validate_search(request.form)
    if errors:
        return show_search_again(errors, 400)

    # Without a key the app still works with manual options (docs/decisions.md, D6).
    api_key = current_app.config.get("GOOGLE_MAPS_API_KEY")
    if not api_key:
        return show_search_again([PLACES_UNAVAILABLE_MESSAGE], 503)
    try:
        place_ids = places.search_nearby(
            api_key=api_key,
            latitude=search["latitude"],
            longitude=search["longitude"],
            radius_m=search["radius_m"],
            category=search["category"],
            max_price_level=search["max_price_level"],
            min_rating=search["min_rating"],
        )
    except places.PlacesError:
        return show_search_again([PLACES_UNAVAILABLE_MESSAGE], 503)

    if not place_ids:
        return show_search_again([NO_PLACES_FOUND_MESSAGE], 200)

    saved = db.save_google_search(
        room_id,
        place_ids,
        search["category"],
        search["latitude"],
        search["longitude"],
        search["radius_m"],
        places.filters_json(search),
    )
    if not saved:
        # Another search claimed the room a moment earlier.
        return show_search_again([places.ALREADY_SUGGESTED_MESSAGE], 400)

    return redirect(url_for("rooms.show_room", room_id=room_id), code=303)


@bp.post("/rooms/<room_id>/surprise")
def surprise_places(room_id: str):
    """F12: the creator runs the surprise search once; a varied mix is saved as options (Post/Redirect/Get)."""
    room = db.get_room(room_id)
    if room is None:
        abort(404)

    # Permission check on the server: hiding the form is not enough.
    participant = db.get_participant(room_id, session_token_for(room_id))
    if participant is None:
        return render_room_page(room, None, errors=[NOT_JOINED_MESSAGE]), 403

    refusal = surprise.surprise_refusal(
        bool(participant["is_creator"]),
        room["mode"],
        room["status"],
        db.has_google_options(room_id),
    )
    if refusal is not None:
        status_code, message = refusal
        return render_room_page(room, participant, search_errors=[message]), status_code

    def show_form_again(messages: list[str], status_code: int):
        """The room page with the entered values and the messages."""
        return render_room_page(
            room,
            participant,
            search_values=places.values_to_show_again(request.form),
            search_errors=messages,
        ), status_code

    search, errors = surprise.validate_surprise(request.form)
    if errors:
        return show_form_again(errors, 400)

    api_key = current_app.config.get("GOOGLE_MAPS_API_KEY")
    if not api_key:
        return show_form_again([PLACES_UNAVAILABLE_MESSAGE], 503)
    try:
        result = surprise.surprise_search(
            api_key=api_key,
            latitude=search["latitude"],
            longitude=search["longitude"],
            radius_m=search["radius_m"],
            category=search["category"],
            max_price_level=search["max_price_level"],
            min_rating=search["min_rating"],
            rng=random.Random(),
        )
    except places.PlacesError:
        return show_form_again([PLACES_UNAVAILABLE_MESSAGE], 503)

    if not result["choices"]:
        return show_form_again([NO_PLACES_FOUND_MESSAGE], 200)

    saved = db.save_search(
        room_id,
        result["choices"],
        search["latitude"],
        search["longitude"],
        result["radius_m"],
        surprise.filters_json(search),
    )
    if not saved:
        # Another search claimed the room a moment earlier.
        return show_form_again([places.ALREADY_SUGGESTED_MESSAGE], 400)

    return redirect(url_for("rooms.show_room", room_id=room_id), code=303)


@bp.post("/rooms/<room_id>/options/<int:option_id>/been-there")
def been_there(room_id: str, option_id: int):
    """F13: a participant has been to this surprise place; replace it with a new one for everyone (Post/Redirect/Get)."""
    room = db.get_room(room_id)
    if room is None:
        abort(404)

    # Every write route checks the token on the server (AGENTS.md, Identity and access).
    participant = db.get_participant(room_id, session_token_for(room_id))
    if participant is None:
        return render_room_page(room, None, errors=[NOT_JOINED_MESSAGE]), 403

    def show_message(message: str, status_code: int):
        """The room page with the message above the options."""
        return render_room_page(room, participant, been_there_errors=[message]), status_code

    room_page = redirect(url_for("rooms.show_room", room_id=room_id), code=303)

    option = db.get_option(room_id, option_id)
    if option is None:
        return show_message(voting_rules.UNKNOWN_OPTION_MESSAGE, 400)
    if room["mode"] != "surprise":
        return show_message(surprise.BEEN_THERE_WRONG_MODE_MESSAGE, 400)
    if room["status"] != "collecting":
        return show_message(places.NOT_COLLECTING_MESSAGE, 400)
    if option["source"] != "google":
        return show_message(surprise.MANUAL_OPTION_MESSAGE, 400)
    if option["is_replaced"]:
        # Someone else pressed it first: AGENTS.md says later requests are ignored.
        return room_page
    if db.count_replaced_options(room_id) >= surprise.MAX_REPLACEMENTS_PER_ROOM:
        return show_message(surprise.REPLACEMENT_LIMIT_MESSAGE, 400)

    api_key = current_app.config.get("GOOGLE_MAPS_API_KEY")
    has_stored_search = room["search_center_lat"] is not None and room["radius_m"] is not None
    if not api_key or not has_stored_search:
        return show_message(PLACES_UNAVAILABLE_MESSAGE, 503)

    # Search the same circle and filters as the surprise search (C4) did.
    filters = surprise.read_filters(room["filters"])
    rng = random.Random()
    active_categories = [
        active["category"] for active in db.get_options(room_id) if active["source"] == "google"
    ]
    try:
        replacement = surprise.find_replacement(
            api_key=api_key,
            latitude=room["search_center_lat"],
            longitude=room["search_center_lng"],
            radius_m=room["radius_m"],
            subcategories=surprise.replacement_subcategories(
                filters["category"], option["category"], active_categories, rng
            ),
            max_price_level=filters["max_price_level"],
            min_rating=filters["min_rating"],
            known_place_ids=set(db.get_room_place_ids(room_id)),
            rng=rng,
        )
    except places.PlacesError:
        return show_message(PLACES_UNAVAILABLE_MESSAGE, 503)

    if replacement is None:
        return show_message(surprise.NOTHING_NEW_MESSAGE, 200)

    new_place_id, category = replacement
    try:
        db.replace_option(room_id, option_id, new_place_id, category)
    except db.INTEGRITY_ERRORS:
        # E.g. another option of this room was replaced by the same place a moment earlier.
        return show_message(OPTION_REFUSED_MESSAGE, 400)
    # Also when replace_option returned False: another request was first, so this one is ignored.
    return room_page


def render_vote_page(room, participant, errors: list[str] | None = None):
    """Render the rating page: the next unrated card, or the overview once everything is rated (F4)."""
    options = db.get_rateable_options(room["id"])
    # Google options have no stored name (Google terms); C2b shows the real name later.
    labels = {option["id"]: option["label"] or GOOGLE_OPTION_LABEL for option in options}
    # Only this participant's own ratings are loaded: nobody sees how others voted.
    own_ratings = db.get_own_ratings(participant["id"])
    # The seed is the token from this browser's session, which nobody else knows.
    order = voting_rules.rating_order(list(labels), session_token_for(room["id"]))
    next_option = voting_rules.next_option_to_rate(order, set(own_ratings))
    # "Option 2 of 5": counts only rateable options, not ratings of replaced ones.
    position = sum(1 for option_id in order if option_id in own_ratings) + 1
    return render_template(
        "vote.html",
        room=room,
        labels=labels,
        order=order,
        own_ratings=own_ratings,
        next_option=next_option,
        position=position,
        rating_labels=voting_rules.RATING_LABELS,
        not_started_message=voting_rules.NOT_STARTED_MESSAGE,
        closed_message=voting_rules.CLOSED_MESSAGE,
        errors=errors or [],
        # Only the creator gets the close button (B3); the close route checks it again.
        is_creator=bool(participant["is_creator"]),
    )


@bp.get("/rooms/<room_id>/vote")
def show_vote(room_id: str):
    """F4: the rating page for the participant whose token is in this browser's session."""
    room = db.get_room(room_id)
    if room is None:
        abort(404)
    participant = db.get_participant(room_id, session_token_for(room_id))
    if participant is None:
        # Visitors join first; the join form is on the room page.
        return redirect(url_for("rooms.show_room", room_id=room_id), code=303)
    return render_vote_page(room, participant)


@bp.post("/rooms/<room_id>/vote")
def save_vote(room_id: str):
    """F4: save one rating, then redirect to the next card (Post/Redirect/Get)."""
    room = db.get_room(room_id)
    if room is None:
        abort(404)

    # Every write route checks the token on the server (AGENTS.md, Identity and access).
    participant = db.get_participant(room_id, session_token_for(room_id))
    if participant is None:
        return render_room_page(room, None, errors=[NOT_JOINED_VOTE_MESSAGE]), 403

    rateable_ids = [option["id"] for option in db.get_rateable_options(room_id)]
    rating = request.form.get("rating")
    option_id = voting_rules.parse_option_id(request.form.get("option_id"))
    errors = voting_rules.vote_errors(room["status"], rating, option_id, rateable_ids)
    if errors:
        return render_vote_page(room, participant, errors), 400

    try:
        # One transaction: the vote and the "done" flag are saved together, or not at all.
        with db.transaction():
            if not db.save_vote(room_id, participant["id"], option_id, rating):
                # The room was closed between the status check above and this write (B3).
                # Return at once: a rejected vote must not change anything else either.
                return render_vote_page(room, participant, [voting_rules.CLOSED_MESSAGE]), 400
            rated_ids = set(db.get_own_ratings(participant["id"]))
            if voting_rules.has_rated_all(rateable_ids, rated_ids):
                db.mark_finished(participant["id"])
    except db.INTEGRITY_ERRORS:
        # E.g. the option was deleted by another request a moment earlier.
        return render_vote_page(room, participant, [VOTE_REFUSED_MESSAGE]), 400

    return redirect(url_for("rooms.show_vote", room_id=room_id), code=303)


@bp.post("/rooms/<room_id>/close")
def close_room(room_id: str):
    """F6: the creator closes the room; the winner is chosen once and stored (Post/Redirect/Get)."""
    room = db.get_room(room_id)
    if room is None:
        abort(404)

    # Creator-only action, checked on the server: hiding the button is not enough.
    participant = db.get_participant(room_id, session_token_for(room_id))
    if participant is None:
        return render_room_page(room, None, errors=[result_rules.ONLY_CREATOR_MESSAGE]), 403
    refusal = result_rules.close_errors(bool(participant["is_creator"]), room["status"])
    if refusal is not None:
        status_code, message = refusal
        return render_vote_page(room, participant, [message]), status_code

    if room["status"] == "voting":
        # One transaction, in this order: claim the room, then read the votes, then store.
        # Because the claim comes first, no vote can be added after the votes are read
        # (save_vote locks the same room row), and only one close can win.
        with db.transaction():
            if db.claim_close(room_id):
                option_ids = [option["id"] for option in db.get_rateable_options(room_id)]
                winner = pick_winner(
                    option_ids,
                    db.get_votes(room_id),
                    db.get_vetoed_option_ids(room_id),
                    # Seeded with the room id: a full tie gives the same winner for this room.
                    rng=random.Random(room_id),
                )
                db.store_result(room_id, winner)
            # If the claim failed, someone else closed the room a moment earlier: their
            # stored result stays and we simply show it.

    # Closing again (or a lost claim) is idempotent: show the existing result.
    return redirect(url_for("rooms.show_result", room_id=room_id), code=303)


@bp.get("/rooms/<room_id>/result")
def show_result(room_id: str):
    """F6: the winner and anonymous counts per option. Who rated what is never shown."""
    room = db.get_room(room_id)
    if room is None:
        abort(404)
    participant = db.get_participant(room_id, session_token_for(room_id))
    if participant is None:
        # Visitors join first; the join form is on the room page.
        return redirect(url_for("rooms.show_room", room_id=room_id), code=303)

    options = db.get_rateable_options(room_id)
    # Google options have no stored name (Google terms); C3 shows the winner's real name.
    labels = {option["id"]: option["label"] or GOOGLE_OPTION_LABEL for option in options}
    counts = result_rules.rating_counts(list(labels), db.get_votes(room_id))
    winner_option_id = db.get_winner_option_id(room_id)
    # C3: card, map and route for the winner. Only the winner is loaded from Google,
    # and only once the room is closed.
    winner = None
    if room["status"] == "closed" and winner_option_id in labels:
        winner_option = next(option for option in db.get_options(room_id) if option["id"] == winner_option_id)
        winner = places.load_winner(
            current_app.config.get("GOOGLE_MAPS_API_KEY"),
            current_app.config.get("GOOGLE_MAPS_EMBED_KEY"),
            winner_option,
        )
    return render_template(
        "result.html",
        room=room,
        labels=labels,
        counts=counts,
        winner_option_id=winner_option_id,
        winner=winner,
        rating_labels=voting_rules.RATING_LABELS,
    )
