"""Fixed groups (A9, F16, specs/a9-groups.md): create a group, join it, plan the next activity."""

from flask import Blueprint, abort, redirect, render_template, request, session, url_for

from app import db
from app.routes.rooms import group_member_for, remember_token
from app.services import groups as group_rules
from app.services import qr
from app.services import rooms as room_rules

bp = Blueprint("groups", __name__)

NOT_MEMBER_PLAN_MESSAGE = "Please join the group before planning an activity."
GROUP_COLLISION_MESSAGE = "Something went wrong while creating the group. Please try again."
NICKNAME_TAKEN_MESSAGE = "This nickname is already taken in this group."
ROOM_COLLISION_MESSAGE = "Something went wrong while creating the room. Please try again."


def remember_group(group_id: str, member_token: str) -> None:
    """Store the member token in the signed session cookie, next to the other groups (like A8).

    With more than 10 groups, the group this browser joined longest ago is forgotten.
    """
    tokens = group_rules.remember_group_token(session.get("group_tokens", {}), group_id, member_token)
    if len(tokens) > group_rules.MAX_REMEMBERED_GROUPS:
        # Called after the member is saved, so the new group counts as the newest.
        keep = group_rules.groups_to_keep(db.get_my_groups(tokens))
        tokens = {key: token for key, token in tokens.items() if key in keep}
    # A new dict is assigned so Flask notices the change and saves the cookie.
    session["group_tokens"] = tokens
    session.permanent = True


def render_group_page(group, member, errors=None, join_nickname="", activity=None):
    """Members see everything; anyone else sees only the group name and the join form."""
    invite_url = url_for("groups.show_group", group_id=group["id"], _external=True)
    members = []
    rooms = []
    if member is not None:
        members = db.get_group_members(group["id"])
        for room in db.get_group_rooms(group["id"]):
            rooms.append(
                {
                    "title": room["title"],
                    "url": url_for(room_rules.room_link_endpoint(room["status"]), room_id=room["id"]),
                    "status_label": room_rules.STATUS_LABELS.get(room["status"], room["status"]),
                }
            )
    return render_template(
        "group.html",
        group=group,
        member=member,
        members=members,
        rooms=rooms,
        invite_url=invite_url,
        qr_svg=qr.invite_qr_svg(invite_url) if member is not None else "",
        errors=errors or [],
        join_nickname=join_nickname,
        activity=activity or {},
        modes=room_rules.MODES,
    )


@bp.get("/groups/new")
def new_group():
    """The "create a group" form."""
    return render_template("new_group.html", form={}, errors=[])


@bp.post("/groups")
def create_group():
    """Save the group and its first member, then show the group page (Post/Redirect/Get)."""
    form, errors = group_rules.validate_new_group(request.form.get("name"), request.form.get("nickname"))
    if errors:
        return render_template("new_group.html", form=form, errors=errors), 400

    group_id = room_rules.new_room_id()
    member_token = room_rules.new_session_token()
    if not db.create_group_with_member(group_id, form["name"], form["nickname"], member_token):
        return render_template("new_group.html", form=form, errors=[GROUP_COLLISION_MESSAGE]), 400

    remember_group(group_id, member_token)
    return redirect(url_for("groups.show_group", group_id=group_id), code=303)


@bp.get("/groups/<group_id>")
def show_group(group_id: str):
    """The group page; its URL is also the invite link."""
    group = db.get_group(group_id)
    if group is None:
        abort(404)
    return render_group_page(group, group_member_for(group_id))


@bp.post("/groups/<group_id>/join")
def join_group(group_id: str):
    """Join the group with a nickname, then show the group page (Post/Redirect/Get)."""
    group = db.get_group(group_id)
    if group is None:
        abort(404)

    # Already a member (e.g. "Join" pressed twice): never create a second member.
    if group_member_for(group_id) is not None:
        return redirect(url_for("groups.show_group", group_id=group_id), code=303)

    nickname = room_rules.clean_text(request.form.get("nickname"))
    taken = [member["nickname"] for member in db.get_group_members(group_id)]
    errors = group_rules.join_group_errors(nickname, taken)
    if errors:
        return render_group_page(group, None, errors, nickname), 400

    member_token = room_rules.new_session_token()
    if not db.add_group_member(group_id, nickname, member_token):
        # Someone took the nickname a moment earlier (e.g. a double tap); nothing was saved.
        return render_group_page(group, None, [NICKNAME_TAKEN_MESSAGE], nickname), 400

    remember_group(group_id, member_token)
    return redirect(url_for("groups.show_group", group_id=group_id), code=303)


@bp.post("/groups/<group_id>/rooms")
def plan_activity(group_id: str):
    """A member starts the group's next activity: a new room with them as its creator."""
    group = db.get_group(group_id)
    if group is None:
        abort(404)

    member = group_member_for(group_id)
    if member is None:
        return render_group_page(group, None, [NOT_MEMBER_PLAN_MESSAGE]), 403

    # The same rules as F1; the nickname is the member's group nickname.
    form, errors = room_rules.validate_new_room(
        request.form.get("title"), request.form.get("mode"), member["nickname"]
    )
    if errors:
        return render_group_page(group, member, errors, activity=form), 400

    room_id = room_rules.new_room_id()
    session_token = room_rules.new_session_token()
    saved = db.create_group_room(
        group_id, room_id, form["title"], form["mode"], member["nickname"], session_token, member["id"]
    )
    if not saved:
        return render_group_page(group, member, [ROOM_COLLISION_MESSAGE], activity=form), 400

    remember_token(room_id, session_token)
    return redirect(url_for("rooms.show_room", room_id=room_id), code=303)
