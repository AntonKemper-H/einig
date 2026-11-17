"""Places from Google Maps (specs: c2-places-search.md, c2b-place-cards.md).

C2a: the Nearby Search call and the search form rules.
C2b: Place Details and photos for the option cards, and the card texts.
C3: the map and the route link for the winner (specs/c3-winner-map.md).
C6: find a place by name with one Text Search (specs/c6-find-place-by-name.md).

Only the place id of each result is kept. Names, photos and ratings are never
stored (Google terms); they are loaded fresh every time a card is shown.
"""

import json
import math
import re

from urllib.parse import urlencode

import requests

NEARBY_SEARCH_URL = "https://places.googleapis.com/v1/places:searchNearby"

# Only the fields we use. Never "*": Google bills by the most expensive field requested.
# rating and priceLevel are needed for the filters below (and C2b shows them).
SEARCH_FIELD_MASK = "places.id,places.rating,places.priceLevel"

TIMEOUT_SECONDS = 5
MAX_RESULT_COUNT = 15

# Google place types the creator can choose, with the text shown in the form.
CATEGORIES = {
    "restaurant": "Restaurant",
    "bar": "Bar",
    "cafe": "Café",
    "movie_theater": "Cinema",
}

# Radius choices as the form sends them (text) with their label.
RADIUS_CHOICES = {"500": "500 m", "1000": "1 km", "2000": "2 km", "5000": "5 km"}
MIN_RATING_CHOICES = {"3.5": "3.5 ★ or more", "4.0": "4.0 ★ or more", "4.5": "4.5 ★ or more"}
PRICE_LEVEL_CHOICES = {"1": "€", "2": "€€", "3": "€€€", "4": "€€€€"}

# Google sends the price level as text. Anything else (e.g. PRICE_LEVEL_UNSPECIFIED)
# counts as "no price level".
PRICE_LEVELS = {
    "PRICE_LEVEL_FREE": 0,
    "PRICE_LEVEL_INEXPENSIVE": 1,
    "PRICE_LEVEL_MODERATE": 2,
    "PRICE_LEVEL_EXPENSIVE": 3,
    "PRICE_LEVEL_VERY_EXPENSIVE": 4,
}

NOT_CREATOR_MESSAGE = "Only the creator can search for places."
WRONG_MODE_MESSAGE = 'Places can only be suggested in a "Places nearby" room.'
NOT_COLLECTING_MESSAGE = "Options can only be added before voting starts."
ALREADY_SUGGESTED_MESSAGE = "Places have already been suggested for this room."


class PlacesError(Exception):
    """Google could not be reached or sent something unusable. The message never contains the key."""


class PlacesUnavailable(PlacesError):
    """Google cannot be reached at all (timeout or no connection), not just "this place failed".

    load_cards() stops calling Google after this, so a page waits for at most one timeout.
    """


def round_coordinate(value: float) -> float:
    """Round a coordinate to 3 decimal places (about 100 m), so no exact location is kept."""
    return round(value, 3)


# --- The Google call ----------------------------------------------------------------

def search_nearby(
    api_key: str,
    latitude: float,
    longitude: float,
    radius_m: int,
    category: str,
    max_price_level: int | None,
    min_rating: float | None,
    included_types: list[str] | None = None,
) -> list[str]:
    """Ask Google for places of one category around a point and return their ids, in Google's order.

    With included_types (F27: all types of the room's kind), those types are searched
    in the same one call instead of the category.
    Raises PlacesError if Google cannot be reached or answers with an error.
    """
    body = {
        "includedTypes": list(included_types) if included_types else [category],
        "maxResultCount": MAX_RESULT_COUNT,
        "locationRestriction": {
            "circle": {
                "center": {"latitude": latitude, "longitude": longitude},
                "radius": radius_m,
            }
        },
    }
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": SEARCH_FIELD_MASK,
    }
    try:
        response = requests.post(
            NEARBY_SEARCH_URL, json=body, headers=headers, timeout=TIMEOUT_SECONDS
        )
    except requests.RequestException:
        # "from None": the original error text could contain the request, and with it the key.
        raise PlacesUnavailable("Google Places could not be reached.") from None

    if response.status_code != 200:
        raise PlacesError(f"Google Places answered with status {response.status_code}.")
    try:
        data = response.json()
    except ValueError:
        raise PlacesError("Google Places sent an answer that is not valid JSON.") from None
    if not isinstance(data, dict):
        raise PlacesError("Google Places sent an answer in an unexpected format.")

    # Google sends {} (no "places") when nothing was found.
    results = data.get("places", [])
    return filter_place_ids(results, max_price_level, min_rating)


def filter_place_ids(
    results: list[dict], max_price_level: int | None, min_rating: float | None
) -> list[str]:
    """Apply the price and rating filters and return the remaining place ids without duplicates.

    Nearby Search has no price or rating parameter, so filtering happens here.
    """
    place_ids = []
    for result in results:
        if not isinstance(result, dict):
            continue
        place_id = result.get("id")
        if not place_id or place_id in place_ids:
            continue
        if max_price_level is not None:
            price_level = PRICE_LEVELS.get(result.get("priceLevel"))
            # Places without a price level are kept: many places have none.
            if price_level is not None and price_level > max_price_level:
                continue
        if min_rating is not None:
            rating = result.get("rating")
            # Places without a rating are dropped: they cannot show they meet the minimum.
            if not isinstance(rating, (int, float)) or rating < min_rating:
                continue
        place_ids.append(place_id)
    return place_ids


# --- Form rules ---------------------------------------------------------------------

def parse_location(latitude_text: str | None, longitude_text: str | None) -> tuple[float, float] | None:
    """Turn the hidden location fields into rounded numbers, or None if they are missing or invalid."""
    try:
        latitude = float(latitude_text or "")
        longitude = float(longitude_text or "")
    except ValueError:
        return None
    # float() also accepts "nan" and "inf", which are no real places.
    if not (math.isfinite(latitude) and math.isfinite(longitude)):
        return None
    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        return None
    return round_coordinate(latitude), round_coordinate(longitude)


def validate_search(form, category_required: bool = True) -> tuple[dict, list[str]]:
    """Clean and check the search form. Returns the typed values and every error message.

    With category_required=False (a room with a setup, F27) the category is neither
    checked nor returned: the room's kind decides what is searched.
    """
    cleaned: dict = {}
    errors = []

    if category_required:
        category = form.get("category") or ""
        if category in CATEGORIES:
            cleaned["category"] = category
        else:
            errors.append("Please choose a category.")

    radius_text = form.get("radius_m") or ""
    if radius_text in RADIUS_CHOICES:
        cleaned["radius_m"] = int(radius_text)
    else:
        errors.append("Please choose a radius.")

    location = parse_location(form.get("latitude"), form.get("longitude"))
    if location is None:
        errors.append("Please share your location so we can search nearby.")
    else:
        cleaned["latitude"], cleaned["longitude"] = location

    # An empty choice means "no filter".
    min_rating_text = form.get("min_rating") or ""
    if min_rating_text == "":
        cleaned["min_rating"] = None
    elif min_rating_text in MIN_RATING_CHOICES:
        cleaned["min_rating"] = float(min_rating_text)
    else:
        errors.append("Please choose a valid minimum rating.")

    price_text = form.get("max_price_level") or ""
    if price_text == "":
        cleaned["max_price_level"] = None
    elif price_text in PRICE_LEVEL_CHOICES:
        cleaned["max_price_level"] = int(price_text)
    else:
        errors.append("Please choose a valid price level.")

    return cleaned, errors


def values_to_show_again(form) -> dict[str, str]:
    """The entered search values for showing the form again after a rejected search.

    The location is shown rounded (or left empty if invalid), so the page never
    repeats a more exact location than the app is allowed to keep.
    """
    values = {
        name: form.get(name) or ""
        for name in ("category", "radius_m", "min_rating", "max_price_level")
    }
    location = parse_location(form.get("latitude"), form.get("longitude"))
    if location is None:
        values["latitude"] = ""
        values["longitude"] = ""
    else:
        values["latitude"] = str(location[0])
        values["longitude"] = str(location[1])
    return values


def search_refusal(
    is_creator: bool, mode: str, status: str, already_suggested: bool
) -> tuple[int, str] | None:
    """Return (HTTP status, message) if this participant may not search in this room, else None.

    Used by the route (to reject a search) and by the room page (to hide the form).
    """
    if not is_creator:
        return 403, NOT_CREATOR_MESSAGE
    if mode != "nearby":
        return 400, WRONG_MODE_MESSAGE
    if status != "collecting":
        return 400, NOT_COLLECTING_MESSAGE
    if already_suggested:
        return 400, ALREADY_SUGGESTED_MESSAGE
    return None


def filters_json(search: dict, kind: str | None = None) -> str:
    """The filters as JSON text for the room's `filters` column (C4 reuses them).

    In a room with a setup (F27) the category is null and the kind ("food.brunch") is stored.
    """
    filters = {
        "category": search.get("category"),
        "min_rating": search["min_rating"],
        "max_price_level": search["max_price_level"],
    }
    if kind is not None:
        filters["kind"] = kind
    return json.dumps(filters)


# --- C2b: Place Details and photos ---------------------------------------------------

PLACE_DETAILS_URL = "https://places.googleapis.com/v1/places/"
# Only what the card shows. Never "*" (billing depends on the most expensive field).
DETAILS_FIELD_MASK = "displayName,rating,priceLevel,location,photos"
PHOTO_MEDIA_URL = "https://places.googleapis.com/v1/{photo_name}/media"
PHOTO_MAX_WIDTH_PX = 400
FALLBACK_PLACE_NAME = "Place from Google Maps"
EARTH_RADIUS_M = 6_371_000

# Google ids only contain these characters. Checking them before they go into a URL
# means nobody can make our server call another address or another API path.
PLACE_ID_PATTERN = re.compile(r"[A-Za-z0-9_-]+")
PHOTO_NAME_PATTERN = re.compile(r"places/([A-Za-z0-9_-]+)/photos/([A-Za-z0-9_-]+)")


def photo_place_id(photo_name: str) -> str | None:
    """Return the place id inside a photo name like places/<id>/photos/<ref>, or None if it has another form."""
    match = PHOTO_NAME_PATTERN.fullmatch(photo_name or "")
    return match.group(1) if match else None


def is_number(value) -> bool:
    """True for int and float values (but not True/False, which Python also counts as int)."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def get_place_details(api_key: str, place_id: str) -> dict:
    """Load name, rating, price level, location and first photo of one place from Google.

    Raises PlacesUnavailable if Google cannot be reached, PlacesError for any other problem.
    """
    if not isinstance(place_id, str) or not PLACE_ID_PATTERN.fullmatch(place_id):
        raise PlacesError("This is not a valid place id.")
    headers = {"X-Goog-Api-Key": api_key, "X-Goog-FieldMask": DETAILS_FIELD_MASK}
    try:
        response = requests.get(
            PLACE_DETAILS_URL + place_id, headers=headers, timeout=TIMEOUT_SECONDS
        )
    except requests.RequestException:
        raise PlacesUnavailable("Google Places could not be reached.") from None

    if response.status_code != 200:
        raise PlacesError(f"Google Places answered with status {response.status_code}.")
    try:
        data = response.json()
    except ValueError:
        raise PlacesError("Google Places sent an answer that is not valid JSON.") from None
    if not isinstance(data, dict):
        raise PlacesError("Google Places sent an answer in an unexpected format.")
    return read_details(place_id, data)


def read_details(place_id: str, data: dict) -> dict:
    """Pick the card fields out of Google's answer. Anything missing or unusable becomes None."""
    details = {
        "name": None,
        "rating": None,
        "price_level": None,
        "latitude": None,
        "longitude": None,
        "photo_name": None,
        "photo_author": None,
        "photo_author_uri": None,
    }

    display_name = data.get("displayName")
    if isinstance(display_name, dict) and isinstance(display_name.get("text"), str):
        details["name"] = display_name["text"] or None

    if is_number(data.get("rating")):
        details["rating"] = data["rating"]

    price_text = data.get("priceLevel")
    if isinstance(price_text, str):
        details["price_level"] = PRICE_LEVELS.get(price_text)

    location = data.get("location")
    if isinstance(location, dict) and is_number(location.get("latitude")) and is_number(
        location.get("longitude")
    ):
        details["latitude"] = location["latitude"]
        details["longitude"] = location["longitude"]

    photos = data.get("photos")
    if isinstance(photos, list) and photos and isinstance(photos[0], dict):
        first_photo = photos[0]
        photo_name = first_photo.get("name")
        # Only a photo of this very place, so the proxy check (photo -> place -> room) holds.
        if isinstance(photo_name, str) and photo_place_id(photo_name) == place_id:
            details["photo_name"] = photo_name
        authors = first_photo.get("authorAttributions")
        if isinstance(authors, list) and authors and isinstance(authors[0], dict):
            author = authors[0]
            if isinstance(author.get("displayName"), str):
                details["photo_author"] = author["displayName"] or None
            uri = author.get("uri")
            # Only https links: a "javascript:" link would run code when tapped.
            if isinstance(uri, str) and uri.startswith("https://"):
                details["photo_author_uri"] = uri
    return details


def fetch_photo(api_key: str, photo_name: str) -> tuple[bytes, str]:
    """Load one photo from Google and return its bytes and content type.

    requests follows Google's redirect to the image, so the browser never sees
    the key or the redirect address. Raises PlacesError if anything goes wrong.
    """
    if photo_place_id(photo_name) is None:
        raise PlacesError("This is not a valid photo name.")
    try:
        response = requests.get(
            PHOTO_MEDIA_URL.format(photo_name=photo_name),
            params={"maxWidthPx": PHOTO_MAX_WIDTH_PX},
            headers={"X-Goog-Api-Key": api_key},
            timeout=TIMEOUT_SECONDS,
        )
    except requests.RequestException:
        raise PlacesUnavailable("Google Places could not be reached.") from None
    if response.status_code != 200:
        raise PlacesError(f"Google Places answered with status {response.status_code}.")
    content_type = response.headers.get("Content-Type", "")
    if not content_type.startswith("image/"):
        raise PlacesError("Google Places did not send an image.")
    return response.content, content_type


# --- C2b: card texts ------------------------------------------------------------------

def distance_m(latitude_1: float, longitude_1: float, latitude_2: float, longitude_2: float) -> int:
    """Distance between two points in whole metres (haversine formula: distance on a sphere)."""
    lat_1, lat_2 = math.radians(latitude_1), math.radians(latitude_2)
    lat_difference = lat_2 - lat_1
    lng_difference = math.radians(longitude_2 - longitude_1)
    a = (
        math.sin(lat_difference / 2) ** 2
        + math.cos(lat_1) * math.cos(lat_2) * math.sin(lng_difference / 2) ** 2
    )
    return round(2 * EARTH_RADIUS_M * math.asin(math.sqrt(a)))


def format_distance(metres: int) -> str:
    """'330 m' below one kilometre (rounded to 10 m), '1.2 km' from one kilometre on."""
    rounded = round(metres / 10) * 10
    if rounded < 1000:
        return f"{rounded} m"
    # max(): 995 m rounds up to 1000 m, which must say "1.0 km", not "0.99 km".
    return f"{max(metres, 1000) / 1000:.1f} km"


def format_price_level(level: int | None) -> str:
    """'Free', '€' … '€€€€', or '' if the price level is unknown."""
    if level is None:
        return ""
    if level == 0:
        return "Free"
    return "€" * level


def format_rating(rating: float | None) -> str:
    """'4.5 ★', or '' if there is no rating."""
    if rating is None:
        return ""
    return f"{rating:.1f} ★"


def build_card(option, details: dict | None, centre_latitude: float | None, centre_longitude: float | None) -> dict:
    """Turn one option and its Google details (or None) into the texts the card template shows."""
    if option["source"] != "google":
        return {"source": "manual", "label": option["label"]}

    if details is None:
        return {
            "source": "google",
            "name": FALLBACK_PLACE_NAME,
            "photo_name": None,
            "photo_author": None,
            "photo_author_uri": None,
            "rating_text": "",
            "price_text": "",
            "distance_text": "",
            "details_missing": True,
        }

    distance_text = ""
    coordinates = (centre_latitude, centre_longitude, details["latitude"], details["longitude"])
    if all(value is not None for value in coordinates):
        distance_text = format_distance(distance_m(*coordinates))

    return {
        "source": "google",
        "name": details["name"] or FALLBACK_PLACE_NAME,
        "photo_name": details["photo_name"],
        "photo_author": details["photo_author"],
        "photo_author_uri": details["photo_author_uri"],
        "rating_text": format_rating(details["rating"]),
        "price_text": format_price_level(details["price_level"]),
        "distance_text": distance_text,
        "details_missing": False,
    }


def load_cards(
    api_key: str | None, options, centre_latitude: float | None, centre_longitude: float | None
) -> list[dict]:
    """One card per option, in order. Loads Google details once per Google option.

    Without a key, or once Google turned out to be unreachable, Google options get
    the fallback card without further calls: the calls run one after another with a
    5-second timeout each, so 15 slow calls would take longer than the server allows.
    """
    google_reachable = bool(api_key)
    cards = []
    for option in options:
        details = None
        if option["source"] == "google" and google_reachable:
            try:
                details = get_place_details(api_key, option["place_id"])
            except PlacesUnavailable:
                google_reachable = False
            except PlacesError:
                pass  # Only this place failed; the next one is still loaded.
        cards.append(build_card(option, details, centre_latitude, centre_longitude))
    return cards


# --- C3: map and route to the winner -----------------------------------------

EMBED_PLACE_URL = "https://www.google.com/maps/embed/v1/place"
ROUTE_URL = "https://www.google.com/maps/dir/"


def map_embed_url(embed_key: str | None, place_id: str) -> str | None:
    """The Maps Embed URL that shows this place, or None without an embed key or with a bad place id.

    The embed key is the browser key restricted to our domain, so it may appear in the page.
    """
    if not embed_key or not PLACE_ID_PATTERN.fullmatch(place_id):
        return None
    return EMBED_PLACE_URL + "?" + urlencode({"key": embed_key, "q": "place_id:" + place_id})


def route_url(place_id: str, name: str) -> str | None:
    """A Google Maps link that opens the route to this place (no key, no API call), or None for a bad place id.

    The place id decides the destination; the name is only shown while Google Maps loads.
    """
    if not PLACE_ID_PATTERN.fullmatch(place_id):
        return None
    query = {"api": "1", "destination": name, "destination_place_id": place_id}
    return ROUTE_URL + "?" + urlencode(query)


def load_winner(api_key: str | None, embed_key: str | None, option, card: dict | None = None) -> dict:
    """The card, map URL and route URL the result page shows for the winning option.

    Manual options have no location, so they get neither map nor route and Google is not called.
    Map and route only need the place id, so they stay even when the details fail.
    If the caller already loaded the winner's card (C2c), it is reused and Google is not called.
    """
    if option["source"] != "google":
        return {"card": build_card(option, None, None, None), "map_url": None, "route_url": None}
    if card is None:
        # No centre: it is deleted when the room closes (privacy), so the card has no distance.
        card = load_cards(api_key, [option], None, None)[0]
    return {
        "card": card,
        "map_url": map_embed_url(embed_key, option["place_id"]),
        "route_url": route_url(option["place_id"], card["name"]),
    }


# --- C6: find a place by name (F23, specs/c6-find-place-by-name.md) ---------------

TEXT_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
# Name and address let the participant see which match is the right one. Because of
# them every search is billed as Text Search Pro (D14), so no other field is asked for.
NAME_SEARCH_FIELD_MASK = "places.id,places.displayName,places.formattedAddress"
NAME_SEARCH_PAGE_SIZE = 5
# Only a bias, not a limit: a place the participant names may be further away.
NAME_SEARCH_BIAS_RADIUS_M = 5000
# Soft guard against repeated searches (reloads, double taps), counted in the session.
MAX_NAME_SEARCHES = 10
NAME_MAX_LENGTH = 80

EMPTY_NAME_MESSAGE = "Please enter a name to search for."
LONG_NAME_MESSAGE = f"A name can be at most {NAME_MAX_LENGTH} characters."
NAME_SEARCH_LIMIT_MESSAGE = (
    f"You have already searched {MAX_NAME_SEARCHES} times in this room."
    " You can still add options yourself."
)
NO_MATCHES_MESSAGE = "No places found with this name. You can still add it as your own option."
EXPIRED_MATCHES_MESSAGE = "This search result has expired. Please search again."
ALREADY_AN_OPTION_MESSAGE = "This place is already an option."


def validate_name(value: str | None) -> tuple[str, list[str]]:
    """Strip the typed name and return it with the error messages (empty list if it is fine)."""
    name = (value or "").strip()
    if not name:
        return name, [EMPTY_NAME_MESSAGE]
    if len(name) > NAME_MAX_LENGTH:
        return name, [LONG_NAME_MESSAGE]
    return name, []


def search_by_name(
    api_key: str, name: str, latitude: float | None, longitude: float | None
) -> list[dict]:
    """Ask Google for places with this name (one Text Search) and return at most 5 matches.

    Each match is {"place_id", "name", "address"}. With a location, places near it
    come first. Raises PlacesError if Google cannot be reached or answers with an error.
    """
    body: dict = {"textQuery": name, "pageSize": NAME_SEARCH_PAGE_SIZE}
    if latitude is not None and longitude is not None:
        body["locationBias"] = {
            "circle": {
                "center": {"latitude": latitude, "longitude": longitude},
                "radius": NAME_SEARCH_BIAS_RADIUS_M,
            }
        }
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": NAME_SEARCH_FIELD_MASK,
    }
    try:
        response = requests.post(
            TEXT_SEARCH_URL, json=body, headers=headers, timeout=TIMEOUT_SECONDS
        )
    except requests.RequestException:
        # "from None": the original error text could contain the request, and with it the key.
        raise PlacesUnavailable("Google Places could not be reached.") from None

    if response.status_code != 200:
        raise PlacesError(f"Google Places answered with status {response.status_code}.")
    try:
        data = response.json()
    except ValueError:
        raise PlacesError("Google Places sent an answer that is not valid JSON.") from None
    if not isinstance(data, dict):
        raise PlacesError("Google Places sent an answer in an unexpected format.")
    # Google sends {} (no "places") when nothing was found.
    return read_matches(data.get("places", []))


def read_matches(results) -> list[dict]:
    """Pick id, name and address out of Google's results: valid ids only, no duplicates, at most 5."""
    matches: list[dict] = []
    seen_ids: set[str] = set()
    if not isinstance(results, list):
        return matches
    for result in results:
        if len(matches) == NAME_SEARCH_PAGE_SIZE:
            break
        if not isinstance(result, dict):
            continue
        place_id = result.get("id")
        # Only ids of the expected form: they are posted back in step 2 and used in URLs.
        if not isinstance(place_id, str) or not PLACE_ID_PATTERN.fullmatch(place_id):
            continue
        if place_id in seen_ids:
            continue
        seen_ids.add(place_id)

        name = None
        display_name = result.get("displayName")
        if isinstance(display_name, dict) and isinstance(display_name.get("text"), str):
            name = display_name["text"]
        address = result.get("formattedAddress")
        matches.append(
            {
                "place_id": place_id,
                "name": name or FALLBACK_PLACE_NAME,
                "address": address if isinstance(address, str) else "",
            }
        )
    return matches
