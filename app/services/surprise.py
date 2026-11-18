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
    category: str | None,
    max_price_level: int | None,
    min_rating: float | None,
    rng: random.Random,
    subcategory_pool: list[str] | None = None,
) -> dict:
    """Search a few random sub-categories, widen the radius if too little is found, and pick a varied mix.

    With subcategory_pool (F27: the types of the room's kind), the sub-categories are
    chosen from that list instead of SUBCATEGORIES[category].

    Returns {"choices": [(place id, sub-category), ...], "radius_m": radius of the last round}.
    Any PlacesError stops everything at once and is raised: after a timeout, waiting
    for up to 15 more calls would take longer than the server allows.
    """
    if subcategory_pool:
        subcategories = rng.sample(
            subcategory_pool, min(SUBCATEGORIES_PER_SEARCH, len(subcategory_pool))
        )
    else:
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


def filters_json(search: dict, kind: str | None = None) -> str:
    """The filters as JSON text for the room's `filters` column, with the radius the creator chose.

    In a room with a setup (F27) the category is null and the kind ("food.brunch") is stored.
    """
    filters = {
        "category": search.get("category"),
        "min_rating": search["min_rating"],
        "max_price_level": search["max_price_level"],
        "requested_radius_m": search["radius_m"],
    }
    if kind is not None:
        filters["kind"] = kind
    return json.dumps(filters)


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


# --- "Been there": replace one place (F13, spec: specs/c5-been-there.md) ------------

# A cost guard: every replacement asks Google again, so one person pressing the
# button again and again must not run up the bill.
MAX_REPLACEMENTS_PER_ROOM = 5

BEEN_THERE_WRONG_MODE_MESSAGE = '"Been there" is only available in a "Surprise me" room.'
MANUAL_OPTION_MESSAGE = "Only places from Google Maps can be replaced."
# Places found by name (C6) have no sub-category and are no surprise (specs/c6-find-place-by-name.md).
PICKED_PLACE_MESSAGE = "Only places from the surprise search can be replaced."
REPLACEMENT_LIMIT_MESSAGE = (
    f"This room has already replaced {MAX_REPLACEMENTS_PER_ROOM} places."
    " You can still add options yourself."
)
NOTHING_NEW_MESSAGE = (
    "No other place was found nearby, so this place stays. You can still add options yourself."
)


def read_filters(filters_text: str | None) -> dict:
    """Read the main category and the filters from the room's `filters` JSON.

    Anything missing or of the wrong type becomes None, so a damaged value never
    stops the group: the replacement then simply searches without that filter.
    """
    filters = {"category": None, "min_rating": None, "max_price_level": None}
    try:
        data = json.loads(filters_text) if filters_text else {}
    except ValueError:
        return filters
    if not isinstance(data, dict):
        return filters

    if data.get("category") in SUBCATEGORIES:
        filters["category"] = data["category"]
    if places.is_number(data.get("min_rating")):
        filters["min_rating"] = float(data["min_rating"])
    max_price_level = data.get("max_price_level")
    if isinstance(max_price_level, int) and not isinstance(max_price_level, bool):
        filters["max_price_level"] = max_price_level
    return filters


def replacement_subcategories(
    main_category: str | None,
    replaced_subcategory: str,
    active_subcategories: list[str],
    rng: random.Random,
) -> list[str]:
    """The one or two sub-categories to search for a new place, in order.

    The same kind first (a Thai place is replaced by another Thai place), so the
    variety of the options stays. As a fallback one other kind, preferably one that
    no option of the room has yet, again for variety.
    """
    if main_category not in SUBCATEGORIES:
        return [replaced_subcategory]
    others = [kind for kind in SUBCATEGORIES[main_category] if kind != replaced_subcategory]
    unused = [kind for kind in others if kind not in active_subcategories]
    candidates = unused or others
    if not candidates:
        return [replaced_subcategory]
    return [replaced_subcategory, rng.choice(candidates)]


def pick_replacement(place_ids: list[str], known_place_ids: set[str], rng: random.Random) -> str | None:
    """A random place id that the room has never had, or None if there is none.

    Random instead of Google's first: Google sorts by popularity, and a surprise
    should not always be the best-known place. The known ids include replaced
    places, so a place someone has been to never comes back.
    """
    new_place_ids = [place_id for place_id in place_ids if place_id not in known_place_ids]
    if not new_place_ids:
        return None
    return rng.choice(new_place_ids)


def find_replacement(
    api_key: str,
    latitude: float,
    longitude: float,
    radius_m: int,
    subcategories: list[str],
    max_price_level: int | None,
    min_rating: float | None,
    known_place_ids: set[str],
    rng: random.Random,
) -> tuple[str, str] | None:
    """Search the sub-categories in order and return (place id, sub-category) of the first new place.

    Returns None if none of them has a new place. A PlacesError is raised at once,
    without trying the next sub-category.
    """
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
        place_id = pick_replacement(place_ids, known_place_ids, rng)
        if place_id is not None:
            return place_id, subcategory
    return None


def can_press_been_there(mode: str, status: str, source: str) -> bool:
    """True if a card gets the "Been there" button: a Google place in a collecting surprise room."""
    return mode == "surprise" and status == "collecting" and source == "google"
