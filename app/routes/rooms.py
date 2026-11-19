"""Room pages: create a room (F1), show and join it (F2), add and delete options (F3, F24),
lobby and start voting (F7), suggest places nearby (F8), surprise mode (F12),
"Been there" (F13), find a place by name (F23), delete an option (F24),
rating (F4), joker (F10), close the room and show the result (F6), share it (F29), deadline and "everyone done" (F11),
"Join as ..." in a group room (F16), room setup (F27)."""

import random

from flask import (
    Blueprint,
    Response,
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
from app.services import activities, places, qr, share, surprise
from app.services import deadline as deadline_rules
from app.services import lobby as lobby_rules
from app.services import options as option_rules
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
NOT_IN_GROUP_MESSAGE = "You are not a member of this group."
GROUP_NICKNAME_TAKEN_MESSAGE = (
    "Your group nickname is already taken in this room. Please choose another one."
)
ONLY_CREATOR_SETUP_MESSAGE = "Only the creator can set up the room."
SETUP_NOT_COLLECTING_MESSAGE = "The setup can only be changed before voting starts."
ALREADY_SEARCHED_MESSAGE = (
    "The places were already suggested. Changing the activity does not search again."
)


def close_and_store_winner(room_id: str) -> None:
    """Close a voting room and store its winner once (B3 steps, shared with B5).

    One transaction, in this order: claim the room, then read the votes, then store.
    Because the claim comes first, no vote can be added after the votes are read
    (save_vote locks the same room row), and only one close can win. If the claim
    fails, someone else closed the room a moment earlier: their result stays.
    Used by the close button (B3), the deadline and "everyone done" (B5).
    """
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


def close_if_time_is_up(room):
    """F11: close a voting room whose deadline has passed, and return it as it is now.

    There is no background job (Render's free plan has no scheduler), so every page
    of the room calls this first: whoever opens one after the deadline closes the room,
    visitors too. The lobby reloads every 4 seconds, so an open lobby closes it at once.
    """
    if room is None or room["status"] != "voting":
        return room
    if not deadline_rules.is_past(room["deadline"], deadline_rules.now_utc()):
        return room
    close_and_store_winner(room["id"])
    return db.get_room(room["id"])


def time_left_for(room) -> str | None:
    """'Time left: N min' for a voting room with a deadline, else None (F11)."""
    if room["status"] != "voting":
        return None
    return deadline_rules.time_left_text(room["deadline"], deadline_rules.now_utc())


def session_token_for(room_id: str) -> str | None:
    """Return the token this browser stored for the room, or None."""
    return session.get("participant_tokens", {}).get(room_id)


def group_member_for(group_id: str):
    """Return this browser's member row in the group (A9), or None."""
    return db.get_group_member(group_id, session.get("group_tokens", {}).get(group_id))


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


# F23 (C6): how many rooms keep their search count in the session. Only the latest
# room also keeps its matches, so the cookie stays small (review of #39).
MAX_REMEMBERED_NAME_SEARCH_ROOMS = 5


def name_search_entry(room_id: str) -> dict:
    """This browser's name-search state for the room: {"place_ids": [...], "count": n}.

    Anything unexpected in the cookie (e.g. an old format) counts as "no matches, no searches".
    """
    searches = session.get("name_searches")
    entry = searches.get(room_id) if isinstance(searches, dict) else None
    if not isinstance(entry, dict):
        entry = {}
    place_ids = entry.get("place_ids")
    if not isinstance(place_ids, list) or not all(isinstance(item, str) for item in place_ids):
        place_ids = []
    count = entry.get("count")
    if not isinstance(count, int) or isinstance(count, bool) or count < 0:
        count = 0
    return {"place_ids": place_ids, "count": count}


def save_name_search_entry(room_id: str, place_ids: list[str], count: int) -> None:
    """Store the room's matches (ids only, never names) and search count in the signed session.

    Matches of other rooms are dropped, and only the most recent rooms keep their count.
    """
    old = session.get("name_searches")
    searches = {}
    if isinstance(old, dict):
        for other_room_id in old:
            if other_room_id != room_id:
                other = name_search_entry(other_room_id)
                searches[other_room_id] = {"place_ids": [], "count": other["count"]}
    # The current room goes last, so the oldest rooms are the ones dropped below.
    searches[room_id] = {"place_ids": place_ids, "count": count}
    while len(searches) > MAX_REMEMBERED_NAME_SEARCH_ROOMS:
        del searches[next(iter(searches))]
    # A new dict is assigned so Flask notices the change and saves the cookie.
    session["name_searches"] = searches


def invite_url_for(room_id: str) -> str:
    """The full link friends open to join (A2); also what the QR code holds (A6)."""
    return url_for("rooms.show_room", room_id=room_id, _external=True)


def privacy_for(room) -> tuple[bool, bool] | None:
    """A11 (F28): (hide_ideas, reveal_places) while the room is collecting and has a setup, else None.

    None means: show every option, as before A11.
    """
    if room["status"] != "collecting":
        return None
    setup = db.get_room_setup(room["id"])
    if setup is None:
        return None
    return bool(setup["hide_ideas"]), bool(setup["reveal_places"])


def is_hidden_from(room, participant, option) -> bool:
    """True if this option is secret for this participant right now (F28)."""
    privacy = privacy_for(room)
    if privacy is None:
        return False
    shown, _, _ = option_rules.visible_options([option], participant["id"], *privacy)
    return not shown


def is_someone_elses_hidden_idea(room, participant, label: str) -> bool:
    """True if the label is taken only by an option this participant cannot see (F28)."""
    privacy = privacy_for(room)
    if privacy is None:
        return False
    shown, _, _ = option_rules.visible_options(db.get_options(room["id"]), participant["id"], *privacy)
    shown_labels = [option["label"] for option in shown if option["label"] is not None]
    return not option_rules.is_label_taken(label, shown_labels)


def place_taken_message(room, participant, place_id: str) -> str:
    """The message when a place found by name is already in the room (C6, F28).

    If the option holding it is secret for this participant, the same words as for a
    typed idea, so the answer never says whose it is.
    """
    for option in db.get_options(room["id"]):
        if option["place_id"] == place_id and is_hidden_from(room, participant, option):
            return option_rules.SAME_IDEA_MESSAGE
    return places.ALREADY_AN_OPTION_MESSAGE


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
    find_name: str = "",
    find_errors: list[str] | None = None,
    find_matches: list[dict] | None = None,
    offer_group_join: bool = True,
    setup_values: dict | None = None,
    setup_errors: list[str] | None = None,
):
    """Render the room page: join form for visitors; options, add form and place search for participants."""
    invite_url = invite_url_for(room["id"])
    # F27: the room setup, the line everyone sees and this participant's options-per-person count.
    setup = db.get_room_setup(room["id"])
    setup_line = None
    searching_for = None
    options_per_person = None
    if setup is not None:
        setup_line = activities.setup_text(
            setup["activity"], setup["kind"], setup["options_per_person"]
        )
        searching_for = activities.kind_label(setup["activity"], setup["kind"])
        options_per_person = setup["options_per_person"]
    own_option_count = 0
    at_limit = False
    if participant is not None and options_per_person is not None:
        own_option_count = db.count_own_options(room["id"], participant["id"])
        at_limit = activities.limit_reached(own_option_count, options_per_person)
    show_setup_form = (
        participant is not None and bool(participant["is_creator"]) and room["status"] == "collecting"
    )
    if setup_values is None:
        # Pre-filled with the saved setup; empty before the first save.
        # A11: both privacy choices are ticked until the creator saves a setup.
        setup_values = {"kind": "", "options_per_person": "", "hide_ideas": True, "reveal_places": True}
        if setup is not None:
            setup_values = {
                "kind": f"{setup['activity']}.{setup['kind']}",
                "options_per_person": "" if options_per_person is None else str(options_per_person),
                "hide_ideas": bool(setup["hide_ideas"]),
                "reveal_places": bool(setup["reveal_places"]),
            }
    # Open before the first save and while there are errors; collapsed afterwards.
    setup_open = setup is None or bool(setup_errors)
    # C2a/C4 search only once per room: a later setup change does not search again.
    setup_already_searched = show_setup_form and room["radius_m"] is not None
    # Only participants may see the options, so visitors get an empty list
    # (and their page view never calls Google).
    options = db.get_options(room["id"]) if participant else []
    # A11 (F28): while collecting, a room with a setup may keep ideas and places secret.
    # Filtered here, so every page that shows the room (also the 400 error pages) and the
    # Place Details calls below only see the options this participant may see.
    hidden_ideas_text = None
    hidden_places_text = None
    privacy = privacy_for(room) if participant is not None else None
    if privacy is not None:
        options, hidden_ideas, hidden_places = option_rules.visible_options(
            options, participant["id"], *privacy
        )
        if hidden_ideas:
            hidden_ideas_text = option_rules.hidden_ideas_text(hidden_ideas)
        if hidden_places:
            hidden_places_text = option_rules.hidden_places_text(hidden_places)
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
    # A place found by name (C6, no category) is someone's choice, not a surprise: no button.
    been_there_ids = {
        option["id"]
        for option in options
        if surprise.can_press_been_there(room["mode"], room["status"], option["source"])
        and option["category"] is not None
    }
    # F23: every participant can find a place by name while the room is collecting,
    # unless they reached the room's options-per-person limit (F27).
    show_find_form = participant is not None and room["status"] == "collecting" and not at_limit
    room_has_centre = room["search_center_lat"] is not None
    # geolocation.js finds its fields by id, so "Use my location" may appear only once on
    # the page: not here while the creator's search form (C2a/C4) is shown.
    find_offers_location = (
        not room_has_centre and not show_search_form and not show_surprise_form
    )
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
    # A9: a group room links to its group for members, and offers members "Join as ...".
    group = db.get_room_group(room["id"])
    group_member = group_member_for(group["id"]) if group is not None else None
    return render_template(
        "room.html",
        room=room,
        participant=participant,
        group=group,
        group_member=group_member,
        offer_group_join=offer_group_join and group_member is not None,
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
        hidden_ideas_text=hidden_ideas_text,
        hidden_places_text=hidden_places_text,
        show_find_form=show_find_form,
        find_uses_room_centre=room_has_centre,
        find_offers_location=find_offers_location,
        find_name=find_name,
        find_errors=find_errors or [],
        find_matches=find_matches or [],
        search_values=search_values or {},
        search_errors=search_errors or [],
        categories=places.CATEGORIES,
        radius_choices=places.RADIUS_CHOICES,
        min_rating_choices=places.MIN_RATING_CHOICES,
        price_level_choices=places.PRICE_LEVEL_CHOICES,
        setup_line=setup_line,
        searching_for=searching_for,
        options_per_person=options_per_person,
        own_option_count=own_option_count,
        at_limit=at_limit,
        show_setup_form=show_setup_form,
        setup_open=setup_open,
        setup_values=setup_values,
        setup_errors=setup_errors or [],
        setup_already_searched=setup_already_searched,
        already_searched_message=ALREADY_SEARCHED_MESSAGE,
        kind_choices=activities.kind_choices(),
        options_per_person_choices=activities.OPTIONS_PER_PERSON_CHOICES,
    )


def options_per_person_for(room_id: str) -> int | None:
    """The room's options-per-person limit (F27), or None if the room has no setup or no limit."""
    setup = db.get_room_setup(room_id)
    return None if setup is None else setup["options_per_person"]


def kind_for(room_id: str) -> tuple[str, str] | None:
    """The room's (activity, kind) from its setup (F27), or None if the room has no setup."""
    setup = db.get_room_setup(room_id)
    return None if setup is None else (setup["activity"], setup["kind"])


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
        time_left=time_left_for(room),
        time_limits=deadline_rules.TIME_LIMITS,
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
    room = close_if_time_is_up(db.get_room(room_id))
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

    if request.form.get("as_group_member") == "1":
        return join_as_group_member(room)

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


def join_as_group_member(room):
    """A9: "Join as <nickname>" – join a group room under the group nickname, without typing.

    The nickname always comes from the group membership in the cookie, never from the form.
    """
    group = db.get_room_group(room["id"])
    member = group_member_for(group["id"]) if group is not None else None
    if member is None:
        return render_room_page(room, None, errors=[NOT_IN_GROUP_MESSAGE]), 403

    errors = room_rules.join_errors(member["nickname"], room["status"], db.get_nicknames(room["id"]))
    if errors:
        if room["status"] != "closed":
            # The only other reason: a guest already uses this nickname in the room.
            errors = [GROUP_NICKNAME_TAKEN_MESSAGE]
        # The normal nickname form, so the member can pick another nickname.
        return render_room_page(room, None, errors=errors, offer_group_join=False), 400

    session_token = room_rules.new_session_token()
    if not db.add_group_participant(room["id"], member["nickname"], session_token, member["id"]):
        # Someone took the nickname a moment earlier; nothing was saved.
        return render_room_page(
            room, None, errors=[GROUP_NICKNAME_TAKEN_MESSAGE], offer_group_join=False
        ), 400

    remember_token(room["id"], session_token)
    return redirect(url_for("rooms.show_room", room_id=room["id"]), code=303)


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
    if errors == [option_rules.DUPLICATE_MESSAGE] and is_someone_elses_hidden_idea(room, participant, label):
        # F28: say that the idea exists without showing whose it is.
        errors = [option_rules.SAME_IDEA_MESSAGE]
    if errors:
        return render_room_page(room, participant, option_label=label, option_errors=errors), 400

    options_per_person = options_per_person_for(room_id)
    if options_per_person is None:
        # No limit (no setup, or "Unlimited"): exactly as before F27.
        if not db.add_manual_option(room_id, label, participant["id"]):
            return render_room_page(
                room, participant, option_label=label, option_errors=[OPTION_REFUSED_MESSAGE]
            ), 400
        return redirect(url_for("rooms.show_room", room_id=room_id), code=303)

    def show_option_error(message: str):
        return render_room_page(
            room, participant, option_label=label, option_errors=[message]
        ), 400

    limit_text = activities.limit_message(options_per_person)
    # Fast check for the message; the database decides below (another add may come at the same moment).
    if activities.limit_reached(db.count_own_options(room_id, participant["id"]), options_per_person):
        return show_option_error(limit_text)
    result = db.add_manual_option_within_limit(room_id, label, participant["id"], options_per_person)
    if result == "limit":
        return show_option_error(limit_text)
    if result == "duplicate":
        if is_someone_elses_hidden_idea(room, participant, label):
            return show_option_error(option_rules.SAME_IDEA_MESSAGE)
        return show_option_error(option_rules.DUPLICATE_MESSAGE)
    if result == "not_collecting":
        return show_option_error(option_rules.NOT_COLLECTING_MESSAGE)
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
    if is_hidden_from(room, participant, option):
        # F28: a secret option is answered exactly like an unknown one, so trying ids
        # one by one never shows where hidden ideas are.
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


@bp.post("/rooms/<room_id>/setup")
def save_setup(room_id: str):
    """F27: the creator saves what the group is planning and the options per person (Post/Redirect/Get)."""
    room = db.get_room(room_id)
    if room is None:
        abort(404)

    # Creator-only action, checked on the server: hiding the form is not enough.
    participant = db.get_participant(room_id, session_token_for(room_id))
    if participant is None:
        return render_room_page(room, None, errors=[ONLY_CREATOR_SETUP_MESSAGE]), 403
    if not participant["is_creator"]:
        return render_room_page(room, participant, setup_errors=[ONLY_CREATOR_SETUP_MESSAGE]), 403
    if room["status"] != "collecting":
        return render_room_page(room, participant, setup_errors=[SETUP_NOT_COLLECTING_MESSAGE]), 400

    setup, errors = activities.validate_setup(request.form)
    if errors:
        sent_values = {
            "kind": request.form.get("kind") or "",
            "options_per_person": request.form.get("options_per_person") or "",
            "hide_ideas": bool(request.form.get("hide_ideas")),
            "reveal_places": bool(request.form.get("reveal_places")),
        }
        return render_room_page(
            room, participant, setup_values=sent_values, setup_errors=errors
        ), 400

    # A11 (F28): a manual room has no suggested places, so it always stores "shown".
    reveal_places = setup.get("reveal_places")
    if reveal_places is not None and room["mode"] == "manual":
        reveal_places = 1
    if not db.save_room_setup(
        room_id,
        setup["activity"],
        setup["kind"],
        setup["options_per_person"],
        setup.get("hide_ideas"),
        reveal_places,
    ):
        # The voting started between the check above and the save.
        return render_room_page(room, participant, setup_errors=[SETUP_NOT_COLLECTING_MESSAGE]), 400

    return redirect(url_for("rooms.show_room", room_id=room_id), code=303)


@bp.get("/rooms/<room_id>/lobby")
def show_lobby(room_id: str):
    """F7: the lobby page, which reloads itself every few seconds (meta refresh in the template)."""
    room = close_if_time_is_up(db.get_room(room_id))
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
    # F11: the optional time limit; A5's messages come first.
    minutes, time_limit_errors = deadline_rules.parse_time_limit(request.form.get("time_limit"))
    errors = errors or time_limit_errors
    if errors:
        return render_lobby(room, participant, errors), 400

    deadline = None
    if minutes is not None:
        deadline = deadline_rules.deadline_after(deadline_rules.now_utc(), minutes)
    if not db.start_voting(room_id, deadline):
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

    # F27: in a set-up room the kind decides what is searched; a posted category is ignored.
    kind = kind_for(room_id)
    search, errors = places.validate_search(request.form, category_required=kind is None)
    if errors:
        return show_search_again(errors, 400)
    if kind is None:
        included_types = None
        option_category = search["category"]
        kind_value = None
    else:
        included_types = activities.kind_types(*kind)
        # Every saved place needs a category (that marks it as a search result, not a
        # place picked by name), so the kind's first type is stored.
        option_category = included_types[0]
        kind_value = ".".join(kind)

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
            category=option_category,
            max_price_level=search["max_price_level"],
            min_rating=search["min_rating"],
            included_types=included_types,
        )
    except places.PlacesError:
        return show_search_again([PLACES_UNAVAILABLE_MESSAGE], 503)

    if not place_ids:
        return show_search_again([NO_PLACES_FOUND_MESSAGE], 200)

    saved = db.save_google_search(
        room_id,
        place_ids,
        option_category,
        search["latitude"],
        search["longitude"],
        search["radius_m"],
        places.filters_json(search, kind=kind_value),
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

    # F27: in a set-up room the kind's types are mixed; a posted category is ignored.
    kind = kind_for(room_id)
    if kind is None:
        search, errors = surprise.validate_surprise(request.form)
        subcategory_pool = None
        kind_value = None
    else:
        search, errors = places.validate_search(request.form, category_required=False)
        subcategory_pool = activities.kind_types(*kind)
        kind_value = ".".join(kind)
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
            category=search.get("category"),
            max_price_level=search["max_price_level"],
            min_rating=search["min_rating"],
            rng=random.Random(),
            subcategory_pool=subcategory_pool,
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
        surprise.filters_json(search, kind=kind_value),
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
    if is_hidden_from(room, participant, option):
        # F28: nothing can be done with an option this participant cannot see.
        if option_rules.is_suggested_place(option):
            return show_message(option_rules.BEEN_THERE_SECRET_MESSAGE, 400)
        return show_message(voting_rules.UNKNOWN_OPTION_MESSAGE, 400)
    if room["mode"] != "surprise":
        return show_message(surprise.BEEN_THERE_WRONG_MODE_MESSAGE, 400)
    if room["status"] != "collecting":
        return show_message(places.NOT_COLLECTING_MESSAGE, 400)
    if option["source"] != "google":
        return show_message(surprise.MANUAL_OPTION_MESSAGE, 400)
    if option["category"] is None:
        # Found by name (C6): a deliberate choice with no sub-category to search in.
        return show_message(surprise.PICKED_PLACE_MESSAGE, 400)
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


@bp.post("/rooms/<room_id>/find")
def find_place(room_id: str):
    """F23 step 1: one Text Search for the typed name; the matches are shown in this response.

    No redirect: names and addresses may not be stored anywhere, so they could not be
    shown again after one. Nothing is written to the database here, so a reload cannot
    add anything twice (specs/c6-find-place-by-name.md, decision 1). A reload does send
    the search again: the browser asks first, and it costs one more Google call and
    counts one more search towards the limit (review of #39).
    """
    room = db.get_room(room_id)
    if room is None:
        abort(404)

    # Permission check on the server: hiding the form is not enough.
    participant = db.get_participant(room_id, session_token_for(room_id))
    if participant is None:
        return render_room_page(room, None, errors=[NOT_JOINED_MESSAGE]), 403
    if room["status"] != "collecting":
        return render_room_page(room, participant, find_errors=[places.NOT_COLLECTING_MESSAGE]), 400
    # F27: at the limit the search could not lead to a saved place, so Google is not asked.
    options_per_person = options_per_person_for(room_id)
    if activities.limit_reached(db.count_own_options(room_id, participant["id"]), options_per_person):
        return render_room_page(
            room, participant, find_errors=[activities.limit_message(options_per_person)]
        ), 400

    name, errors = places.validate_name(request.form.get("name"))

    def show_page(status_code: int, messages: list[str], matches: list[dict] | None = None):
        """The room page with the typed name in the find form and in the manual add form."""
        return render_room_page(
            room,
            participant,
            option_label=name,
            find_name=name,
            find_errors=messages,
            find_matches=matches,
        ), status_code

    if errors:
        return show_page(400, errors)

    entry = name_search_entry(room_id)
    if entry["count"] >= places.MAX_NAME_SEARCHES:
        return show_page(400, [places.NAME_SEARCH_LIMIT_MESSAGE])

    # Without a key the app still works with manual options (docs/decisions.md, D6).
    api_key = current_app.config.get("GOOGLE_MAPS_API_KEY")
    if not api_key:
        return show_page(503, [PLACES_UNAVAILABLE_MESSAGE])

    # The room's search centre comes first; otherwise the participant's location, if shared.
    # The participant's location is used for this one call only and never stored.
    if room["search_center_lat"] is not None:
        location = (room["search_center_lat"], room["search_center_lng"])
    else:
        location = places.parse_location(request.form.get("latitude"), request.form.get("longitude"))
    latitude, longitude = location if location is not None else (None, None)

    # Counted before the call: a failed search may also cost a call.
    count = entry["count"] + 1
    try:
        matches = places.search_by_name(api_key, name, latitude, longitude)
    except places.PlacesError:
        save_name_search_entry(room_id, [], count)
        return show_page(503, [PLACES_UNAVAILABLE_MESSAGE])

    # Only the ids of the shown matches are remembered: step 2 accepts nothing else.
    save_name_search_entry(room_id, [match["place_id"] for match in matches], count)
    if not matches:
        return show_page(200, [places.NO_MATCHES_MESSAGE])
    return show_page(200, [], matches)


@bp.post("/rooms/<room_id>/find/add")
def add_found_place(room_id: str):
    """F23 step 2: save the chosen match as a Google option, then redirect (Post/Redirect/Get).

    Never calls Google: the place id must be one of the matches just shown.
    """
    room = db.get_room(room_id)
    if room is None:
        abort(404)

    participant = db.get_participant(room_id, session_token_for(room_id))
    if participant is None:
        return render_room_page(room, None, errors=[NOT_JOINED_MESSAGE]), 403

    def show_message(message: str):
        return render_room_page(room, participant, find_errors=[message]), 400

    if room["status"] != "collecting":
        return show_message(places.NOT_COLLECTING_MESSAGE)

    place_id = request.form.get("place_id") or ""
    entry = name_search_entry(room_id)
    if place_id not in entry["place_ids"]:
        # No search before, an older search, another room, or a made-up id.
        return show_message(places.EXPIRED_MATCHES_MESSAGE)
    # Also replaced places (C5): the group has been there, so it must not come back.
    if place_id in db.get_room_place_ids(room_id):
        return show_message(place_taken_message(room, participant, place_id))

    options_per_person = options_per_person_for(room_id)
    if options_per_person is not None:
        # F27: with a limit, check and insert happen in one transaction. The matches stay
        # in the session when the place is refused, so another one can still be picked.
        limit_text = activities.limit_message(options_per_person)
        if activities.limit_reached(db.count_own_options(room_id, participant["id"]), options_per_person):
            return show_message(limit_text)
        result = db.add_place_option_within_limit(
            room_id, place_id, participant["id"], options_per_person
        )
        if result == "limit":
            return show_message(limit_text)
        if result == "duplicate":
            return show_message(place_taken_message(room, participant, place_id))
        if result == "not_collecting":
            return show_message(places.NOT_COLLECTING_MESSAGE)
        save_name_search_entry(room_id, [], entry["count"])
        return redirect(url_for("rooms.show_room", room_id=room_id), code=303)

    try:
        added = db.add_place_option(room_id, place_id, participant["id"])
    except db.INTEGRITY_ERRORS:
        # The same place added by another request a moment earlier.
        return show_message(place_taken_message(room, participant, place_id))
    if not added:
        # The voting started between the check above and the insert.
        return show_message(places.NOT_COLLECTING_MESSAGE)

    save_name_search_entry(room_id, [], entry["count"])
    return redirect(url_for("rooms.show_room", room_id=room_id), code=303)


def render_vote_page(room, participant, errors: list[str] | None = None):
    """Render the rating page: the next unrated card, or the overview once everything is rated (F4)."""
    options = {option["id"]: option for option in db.get_rateable_options(room["id"])}
    # Only this participant's own ratings are loaded: nobody sees how others voted.
    own_ratings = db.get_own_ratings(participant["id"])
    # The seed is the token from this browser's session, which nobody else knows.
    order = voting_rules.rating_order(list(options), session_token_for(room["id"]))
    next_option = voting_rules.next_option_to_rate(order, set(own_ratings))
    # "Option 2 of 5": counts only rateable options, not ratings of replaced ones.
    position = sum(1 for option_id in order if option_id in own_ratings) + 1

    # C2c: load Google details only for the options this page view shows, because every
    # Place Details call costs quota: the one next card, or every option in the overview.
    shown_ids = []
    if room["status"] == "voting":
        shown_ids = [next_option] if next_option is not None else order
    loaded = places.load_cards(
        current_app.config.get("GOOGLE_MAPS_API_KEY"),
        [options[option_id] for option_id in shown_ids],
        room["search_center_lat"],
        room["search_center_lng"],
    )
    cards = dict(zip(shown_ids, loaded))
    # A10: the next card links to the place's Google Maps page (menu, reviews); no API call.
    menu_url = None
    # Only while voting: outside it no card is loaded (and none is shown).
    if next_option in cards and cards[next_option]["source"] == "google":
        menu_url = places.place_page_url(options[next_option]["place_id"], cards[next_option]["name"])

    # F10: only this participant's own joker (nobody sees who used a joker on what).
    # Its name comes from the cards already loaded; if that option is not shown on this
    # page, only that one option is loaded (at most one extra call, and only after a joker).
    own_veto = db.get_own_veto(room["id"], participant["id"])
    own_veto_name = None
    if room["status"] == "voting" and own_veto in options:
        if own_veto in cards:
            veto_card = cards[own_veto]
        else:
            veto_card = places.load_cards(
                current_app.config.get("GOOGLE_MAPS_API_KEY"),
                [options[own_veto]],
                room["search_center_lat"],
                room["search_center_lng"],
            )[0]
        own_veto_name = veto_card["name"] if veto_card["source"] == "google" else veto_card["label"]
    return render_template(
        "vote.html",
        menu_url=menu_url,
        room=room,
        cards=cards,
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
        own_veto=own_veto,
        own_veto_name=own_veto_name,
        time_left=time_left_for(room),
    )


@bp.get("/rooms/<room_id>/vote")
def show_vote(room_id: str):
    """F4: the rating page for the participant whose token is in this browser's session."""
    room = close_if_time_is_up(db.get_room(room_id))
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
    room = close_if_time_is_up(db.get_room(room_id))
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

    # F11 / concept §3 step 6: when this vote made the last participant done, there is
    # nothing left to wait for, so the room closes now and the voter sees the result.
    if db.everyone_finished(room_id):
        close_and_store_winner(room_id)
        return redirect(url_for("rooms.show_result", room_id=room_id), code=303)
    return redirect(url_for("rooms.show_vote", room_id=room_id), code=303)


@bp.post("/rooms/<room_id>/veto")
def save_veto(room_id: str):
    """F10: use this participant's one joker on an option, then back to the rating page (Post/Redirect/Get)."""
    room = close_if_time_is_up(db.get_room(room_id))
    if room is None:
        abort(404)

    # Every write route checks the token on the server (AGENTS.md, Identity and access).
    participant = db.get_participant(room_id, session_token_for(room_id))
    if participant is None:
        return render_room_page(room, None, errors=[NOT_JOINED_VOTE_MESSAGE]), 403

    rateable_ids = [option["id"] for option in db.get_rateable_options(room_id)]
    option_id = voting_rules.parse_option_id(request.form.get("option_id"))
    own_veto = db.get_own_veto(room_id, participant["id"])
    errors = voting_rules.veto_errors(room["status"], option_id, rateable_ids, own_veto)
    if errors:
        return render_vote_page(room, participant, errors), 400

    try:
        with db.transaction():
            if not db.save_veto(room_id, participant["id"], option_id):
                # The room was closed between the status check above and this write (B3).
                return render_vote_page(room, participant, [voting_rules.CLOSED_MESSAGE]), 400
    except db.INTEGRITY_ERRORS:
        # Two presses at the same moment: the UNIQUE constraint kept the first joker.
        return render_vote_page(room, participant, [voting_rules.JOKER_USED_MESSAGE]), 400

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
        close_and_store_winner(room_id)

    # Closing again (or a lost claim) is idempotent: show the existing result.
    return redirect(url_for("rooms.show_result", room_id=room_id), code=303)


def render_result_page(room, errors: list[str] | None = None):
    """Render the result page (F6): the winner, anonymous counts and the share buttons (F29)."""
    options = db.get_rateable_options(room["id"])
    option_ids = [option["id"] for option in options]
    counts = result_rules.rating_counts(option_ids, db.get_votes(room["id"]))
    # F10: anonymous joker counts only, never who used a joker.
    vetoed_option_ids = db.get_vetoed_option_ids(room["id"])
    joker_counts = result_rules.veto_counts(option_ids, vetoed_option_ids)
    every_option_vetoed = result_rules.every_option_vetoed(option_ids, vetoed_option_ids)
    winner_option_id = db.get_winner_option_id(room["id"])

    # C2c: names for the count list. Google is only called once the room is closed (before
    # that the page shows no list), with one Place Details call per Google option.
    labels = {}
    cards = {}
    winner = None
    if room["status"] == "closed":
        # Without a winner nobody rated anything (every count is 0), so the names are
        # not worth a Google call: the cards fall back without calling Google.
        api_key = current_app.config.get("GOOGLE_MAPS_API_KEY") if winner_option_id is not None else None
        # No centre: B3 deletes it when the room closes, so there is no distance.
        loaded = places.load_cards(api_key, options, None, None)
        cards = dict(zip(option_ids, loaded))
        labels = {
            option_id: card["name"] if card["source"] == "google" else card["label"]
            for option_id, card in cards.items()
        }
        # C3: card, map and route for the winner. Its card is reused, not loaded a second time.
        if winner_option_id in cards:
            winner_option = next(option for option in options if option["id"] == winner_option_id)
            winner = places.load_winner(
                current_app.config.get("GOOGLE_MAPS_API_KEY"),
                current_app.config.get("GOOGLE_MAPS_EMBED_KEY"),
                winner_option,
                card=cards[winner_option_id],
            )
    # F29: share buttons only for a closed room with a winner (D18).
    share_url = None
    if winner is not None:
        share_url = share.whatsapp_url(
            share.share_text(room["title"], labels[winner_option_id], winner["route_url"])
        )
    return render_template(
        "result.html",
        room=room,
        labels=labels,
        counts=counts,
        winner_option_id=winner_option_id,
        winner=winner,
        rating_labels=voting_rules.RATING_LABELS,
        joker_counts=joker_counts,
        every_option_vetoed=every_option_vetoed,
        share_url=share_url,
        errors=errors or [],
    )


@bp.get("/rooms/<room_id>/result")
def show_result(room_id: str):
    """F6: the winner and anonymous counts per option. Who rated what is never shown."""
    room = close_if_time_is_up(db.get_room(room_id))
    if room is None:
        abort(404)
    participant = db.get_participant(room_id, session_token_for(room_id))
    if participant is None:
        # Visitors join first; the join form is on the room page.
        return redirect(url_for("rooms.show_room", room_id=room_id), code=303)

    return render_result_page(room)


@bp.get("/rooms/<room_id>/calendar.ics")
def calendar_file(room_id: str):
    """F29: the group's choice as a calendar file, at the date and time the participant entered.

    A GET, because nothing is stored: the file is built from the form and the stored
    winner, and reloading it is harmless (D18, review of #45).
    """
    room = close_if_time_is_up(db.get_room(room_id))
    if room is None:
        abort(404)
    participant = db.get_participant(room_id, session_token_for(room_id))
    if participant is None:
        # Like the result page: visitors join first.
        return redirect(url_for("rooms.show_room", room_id=room_id), code=303)

    winner_option_id = db.get_winner_option_id(room_id)
    if room["status"] != "closed" or winner_option_id is None:
        return render_result_page(room, [share.NO_RESULT_MESSAGE]), 400
    start, errors = share.parse_meeting_time(request.args.get("date"), request.args.get("time"))
    if errors:
        return render_result_page(room, errors), 400

    # The winner's name comes fresh from Google (one Place Details call), never stored.
    winner_option = next(
        option for option in db.get_rateable_options(room_id) if option["id"] == winner_option_id
    )
    winner = places.load_winner(current_app.config.get("GOOGLE_MAPS_API_KEY"), None, winner_option)
    card = winner["card"]
    winner_name = card["name"] if card["source"] == "google" else card["label"]
    body = share.build_ics(
        room_id, room["title"], winner_name, start, winner["route_url"], deadline_rules.now_utc()
    )
    return Response(
        body,
        mimetype="text/calendar",
        headers={"Content-Disposition": 'attachment; filename="einig.ics"'},
    )
