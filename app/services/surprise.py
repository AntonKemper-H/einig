"""Surprise mode: guided randomness (F12, spec: specs/c4-surprise-mode.md).

Instead of the most popular places of one category, the app searches a few
random sub-categories (e.g. Thai, Greek, Mexican), shuffles each result list
and takes one place per sub-category in turn. So the group gets a varied
selection that is different every time.

Every function that uses chance takes an `rng` (a random.Random), so tests can
make the result repeatable with a fixed seed.
"""

import json
import random

from app.services import places

# Google place types ("Table A") mixed for each main category the group can choose.
SUBCATEGORIES = {
    "restaurant": [
        "italian_restaurant",
        "japanese_restaurant",
        "mexican_restaurant",
        "indian_restaurant",
        "thai_restaurant",
        "greek_restaurant",
        "vietnamese_restaurant",
        "turkish_restaurant",
        "chinese_restaurant",
        "korean_restaurant",
        "spanish_restaurant",
        "lebanese_restaurant",
        "vegan_restaurant",
    ],
    "bar": ["bar", "pub", "wine_bar", "bar_and_grill"],
    "cafe": ["cafe", "coffee_shop", "tea_house", "dessert_shop"],
}

# Text shown in the form for each main category.
CATEGORY_LABELS = {"restaurant": "Any restaurant", "bar": "Any bar", "cafe": "Any café"}

SUBCATEGORIES_PER_SEARCH = 4  # how many sub-categories are searched per room
SURPRISE_OPTION_COUNT = 5  # how many places are saved as options
WIDENING_FACTOR = 1.5  # F12: "+50 %" ...
MAX_WIDENINGS = 3  # ... "at most three times"

WRONG_MODE_MESSAGE = 'Surprise places can only be suggested in a "Surprise me" room.'
CATEGORY_MESSAGE = "Please choose a category."


# --- Guided randomness (pure functions) ---------------------------------------------

def choose_subcategories(category: str, rng: random.Random) -> list[str]:
    """Pick SUBCATEGORIES_PER_SEARCH different sub-categories of the main category at random."""
    subcategories = SUBCATEGORIES[category]
    # rng.sample also shuffles, so a small category comes back complete, in random order.
    return rng.sample(subcategories, min(SUBCATEGORIES_PER_SEARCH, len(subcategories)))


def widened_radius(radius_m: int) -> int:
    """The next, 50 % larger search radius in whole metres."""
    return round(radius_m * WIDENING_FACTOR)


def count_distinct(results: list[tuple[str, list[str]]]) -> int:
    """How many different place ids all search results contain together."""
    return len({place_id for _, place_ids in results for place_id in place_ids})


def pick_varied(
    results: list[tuple[str, list[str]]], count: int, rng: random.Random
) -> list[tuple[str, str]]:
    """Pick up to `count` (place id, sub-category) pairs, one per sub-category in turn.

    Each list is shuffled first: Google sorts by popularity, so without shuffling
    the group would always get the best-known place of each kind, which is the
    opposite of a surprise. Taking one place per sub-category in turn (round robin)
    means no two options share a sub-category while others still have places.
    """
    # Shuffled copies, so the caller's lists stay unchanged.
    queues = []
    for subcategory, place_ids in results:
        shuffled = list(place_ids)
        rng.shuffle(shuffled)
        queues.append((subcategory, shuffled))

    picked: list[tuple[str, str]] = []
    picked_ids: set[str] = set()
    while len(picked) < count and any(place_ids for _, place_ids in queues):
        # One round: at most one new place from every sub-category.
        for subcategory, place_ids in queues:
            if len(picked) == count:
                break
            # Skip places already picked under another type (Google can list one place twice).
            while place_ids and place_ids[0] in picked_ids:
                place_ids.pop(0)
            if place_ids:
                place_id = place_ids.pop(0)
                picked.append((place_id, subcategory))
                picked_ids.add(place_id)
    return picked


# --- The search rounds --------------------------------------------------------------

def surprise_search(
    api_key: str,
    latitude: float,
    longitude: float,
    radius_m: int,
    category: str,
    max_price_level: int | None,
    min_rating: float | None,
    rng: random.Random,
) -> dict:
    """Search a few random sub-categories, widen the radius if too little is found, and pick a varied mix.

    Returns {"choices": [(place id, sub-category), ...], "radius_m": radius of the last round}.
    Any PlacesError stops everything at once and is raised: after a timeout, waiting
    for up to 15 more calls would take longer than the server allows.
    """
    subcategories = choose_subcategories(category, rng)
    widenings = 0
    while True:
        results = []
        for subcategory in subcategories:
            place_ids = places.search_nearby(
                api_key=api_key,
                latitude=latitude,
                longitude=longitude,
                radius_m=radius_m,
                category=subcategory,
                max_price_level=max_price_level,
                min_rating=min_rating,
            )
            results.append((subcategory, place_ids))
        if count_distinct(results) >= SURPRISE_OPTION_COUNT or widenings == MAX_WIDENINGS:
            break
        radius_m = widened_radius(radius_m)
        widenings += 1

    # Only the last round counts: it searched the largest circle, and the stored
    # radius then matches the options.
    return {"choices": pick_varied(results, SURPRISE_OPTION_COUNT, rng), "radius_m": radius_m}


# --- Form rules -------------------------------------------------------------------

def validate_surprise(form) -> tuple[dict, list[str]]:
    """Clean and check the surprise form: C2a's rules, but only the main categories of SUBCATEGORIES."""
    cleaned, errors = places.validate_search(form)
    category = form.get("category") or ""
    if category not in SUBCATEGORIES:
        cleaned.pop("category", None)
        # C2a already reported an unknown category; add the message only if it accepted it (movie_theater).
        if CATEGORY_MESSAGE not in errors:
            errors.insert(0, CATEGORY_MESSAGE)
    return cleaned, errors


def surprise_refusal(
    is_creator: bool, mode: str, status: str, already_suggested: bool
) -> tuple[int, str] | None:
    """Return (HTTP status, message) if this participant may not run the surprise search, else None.

    Same order and messages as C2a's search_refusal, except for the room mode.
    """
    if not is_creator:
        return 403, places.NOT_CREATOR_MESSAGE
    if mode != "surprise":
        return 400, WRONG_MODE_MESSAGE
    if status != "collecting":
        return 400, places.NOT_COLLECTING_MESSAGE
    if already_suggested:
        return 400, places.ALREADY_SUGGESTED_MESSAGE
    return None


def filters_json(search: dict) -> str:
    """The filters as JSON text for the room's `filters` column, with the radius the creator chose."""
    return json.dumps(
        {
            "category": search["category"],
            "min_rating": search["min_rating"],
            "max_price_level": search["max_price_level"],
            "requested_radius_m": search["radius_m"],
        }
    )


def widened_to_text(mode: str, radius_m: int | None, filters: str | None) -> str | None:
    """The radius the search was widened to (e.g. '1.5 km'), or None if it was not widened."""
    if mode != "surprise" or radius_m is None or not filters:
        return None
    try:
        requested = json.loads(filters).get("requested_radius_m")
    except (ValueError, AttributeError):
        return None
    if not isinstance(requested, int) or radius_m <= requested:
        return None
    return places.format_distance(radius_m)
