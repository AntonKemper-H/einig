"""Files the browser loads directly. For now: the place photo proxy (C2b, specs/c2b-place-cards.md).

The manifest and the service worker (PWA) will join this blueprint later.
"""

from flask import Blueprint, Response, abort, current_app, session

from app import db
from app.services import places

bp = Blueprint("pwa", __name__)

PHOTO_UNAVAILABLE_MESSAGE = "Photo not available."
# The browser may keep a photo for 10 minutes; "private" means only this browser, no shared caches.
PHOTO_CACHE_CONTROL = "private, max-age=600"


def browser_has_joined_room_with_place(place_id: str) -> bool:
    """True if this browser is a participant of a room that has this place as a Google option."""
    for room_id, session_token in session.get("participant_tokens", {}).items():
        if db.get_participant(room_id, session_token) is None:
            continue
        if db.room_has_google_place(room_id, place_id):
            return True
    return False


def photo_unavailable() -> tuple[str, int, dict[str, str]]:
    """Plain-text answer when the photo cannot be loaded; the card still shows everything else."""
    return PHOTO_UNAVAILABLE_MESSAGE, 503, {"Content-Type": "text/plain; charset=utf-8"}


@bp.get("/photo/<path:photo_name>")
def photo(photo_name: str):
    """Load a place photo from Google on the server, so the API key never reaches the browser."""
    place_id = places.photo_place_id(photo_name)
    if place_id is None:
        abort(404)
    # Without this check, anyone could use our server and our quota to load any Google photo.
    # The answer is the same 404 as for an unknown URL, so it reveals nothing.
    if not browser_has_joined_room_with_place(place_id):
        abort(404)

    api_key = current_app.config.get("GOOGLE_MAPS_API_KEY")
    if not api_key:
        return photo_unavailable()
    try:
        content, content_type = places.fetch_photo(api_key, photo_name)
    except places.PlacesError:
        return photo_unavailable()

    response = Response(content, content_type=content_type)
    response.headers["Cache-Control"] = PHOTO_CACHE_CONTROL
    return response
