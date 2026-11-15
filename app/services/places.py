"""Places from Google Maps: the Nearby Search call and the search form rules (spec: specs/c2-places-search.md).

Only the place id of each result is kept. Names, photos and ratings are never
stored (Google terms); C2b loads them fresh when the cards are shown.
"""

import json
import math

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
) -> list[str]:
    """Ask Google for places of one category around a point and return their ids, in Google's order.

    Raises PlacesError if Google cannot be reached or answers with an error.
    """
    body = {
        "includedTypes": [category],
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
        raise PlacesError("Google Places could not be reached.") from None

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


def validate_search(form) -> tuple[dict, list[str]]:
    """Clean and check the search form. Returns the typed values and every error message."""
    cleaned: dict = {}
    errors = []

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


def filters_json(search: dict) -> str:
    """The filters as JSON text for the room's `filters` column (C4 reuses them)."""
    return json.dumps(
        {
            "category": search["category"],
            "min_rating": search["min_rating"],
            "max_price_level": search["max_price_level"],
        }
    )
