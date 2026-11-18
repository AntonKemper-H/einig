"""F27 room setup: what the group is planning and how many options each person may add.

Spec: specs/c9-room-setup.md (decision D17). Pure functions only: no Flask, no database.
"""

# Activity -> kinds -> Google place types ("Table A" of the Places API (New), the types
# allowed in includedTypes). Lunch and dinner are not Google types, so they are no kinds (D17).
# "Climbing" from the spec is left out: Table A has no climbing type.
ACTIVITIES = {
    "food": {
        "label": "Food",
        "kinds": {
            "breakfast": {
                "label": "Breakfast",
                "types": ["breakfast_restaurant", "cafe", "bakery"],
            },
            "brunch": {
                "label": "Brunch",
                "types": ["brunch_restaurant", "breakfast_restaurant", "cafe"],
            },
            "restaurant": {
                "label": "Restaurant (lunch or dinner)",
                # Copied from surprise.SUBCATEGORIES["restaurant"], not imported, so this
                # catalogue stays independent of surprise mode.
                "types": [
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
            },
        },
    },
    "drinks": {
        "label": "Drinks & café",
        "kinds": {
            "bar": {"label": "Bar", "types": ["bar", "pub", "wine_bar", "bar_and_grill"]},
            "cafe": {"label": "Café", "types": ["cafe", "coffee_shop", "tea_house"]},
            "dessert": {"label": "Ice cream & dessert", "types": ["ice_cream_shop", "dessert_shop"]},
        },
    },
    "sport": {
        "label": "Sport",
        "kinds": {
            "bowling": {"label": "Bowling", "types": ["bowling_alley"]},
            "swimming": {"label": "Swimming", "types": ["swimming_pool"]},
            "fitness": {"label": "Fitness", "types": ["gym", "fitness_center"]},
            "sports_ground": {"label": "Sports ground", "types": ["sports_complex", "sports_club"]},
        },
    },
    "culture": {
        "label": "Culture & leisure",
        "kinds": {
            "cinema": {"label": "Cinema", "types": ["movie_theater"]},
            "museum": {"label": "Museum & gallery", "types": ["museum", "art_gallery"]},
            "theatre": {"label": "Theatre & concerts", "types": ["performing_arts_theater", "concert_hall"]},
            "amusement": {"label": "Amusement park & zoo", "types": ["amusement_park", "zoo", "aquarium"]},
            "outdoors": {"label": "Park & hiking", "types": ["park", "hiking_area", "national_park"]},
        },
    },
}

OPTIONS_PER_PERSON_CHOICES = [1, 2, 3, 4, 5]

KIND_MESSAGE = "Please choose an activity."
OPTIONS_PER_PERSON_MESSAGE = "Please choose how many options each person can add."


def kind_choices() -> list[tuple[str, list[tuple[str, str]]]]:
    """The choices for the setup select: one group per activity with its kinds as ("activity.kind", label)."""
    return [
        (
            activity["label"],
            [(f"{activity_key}.{kind_key}", kind["label"]) for kind_key, kind in activity["kinds"].items()],
        )
        for activity_key, activity in ACTIVITIES.items()
    ]


def parse_kind(value: str | None) -> tuple[str, str] | None:
    """Turn "food.brunch" into ("food", "brunch"); anything not in the catalogue gives None."""
    if not value:
        return None
    parts = value.split(".")
    if len(parts) != 2:
        return None
    activity, kind = parts
    if activity not in ACTIVITIES or kind not in ACTIVITIES[activity]["kinds"]:
        return None
    return activity, kind


def kind_types(activity: str, kind: str) -> list[str]:
    """The Google place types searched for this kind."""
    return ACTIVITIES[activity]["kinds"][kind]["types"]


def kind_label(activity: str, kind: str) -> str:
    """The text shown for a setup, e.g. "Food – Brunch"."""
    return f"{ACTIVITIES[activity]['label']} – {ACTIVITIES[activity]['kinds'][kind]['label']}"


def parse_options_per_person(value: str | None) -> tuple[int | None, bool]:
    """Read the options-per-person choice: "" means unlimited (None), "1"–"5" a number.

    Returns (number or None, is valid). Anything else is invalid.
    """
    if value == "":
        return None, True
    # Compared as text, so "2.5", "-1" or " 3" never get through int().
    for number in OPTIONS_PER_PERSON_CHOICES:
        if value == str(number):
            return number, True
    return None, False


def validate_setup(form) -> tuple[dict, list[str]]:
    """Check the setup form. Returns {"activity", "kind", "options_per_person"} and every error message."""
    cleaned: dict = {"activity": None, "kind": None, "options_per_person": None}
    errors = []

    parsed_kind = parse_kind(form.get("kind"))
    if parsed_kind is None:
        errors.append(KIND_MESSAGE)
    else:
        cleaned["activity"], cleaned["kind"] = parsed_kind

    options_per_person, valid = parse_options_per_person(form.get("options_per_person"))
    if valid:
        cleaned["options_per_person"] = options_per_person
    else:
        errors.append(OPTIONS_PER_PERSON_MESSAGE)

    return cleaned, errors


def limit_reached(own_option_count: int, options_per_person: int | None) -> bool:
    """True if this person may not add another option (None means unlimited)."""
    if options_per_person is None:
        return False
    return own_option_count >= options_per_person


def setup_text(activity: str, kind: str, options_per_person: int | None) -> str:
    """The line every participant sees, e.g. "Activity: Food – Brunch · Up to 3 options per person"."""
    text = f"Activity: {kind_label(activity, kind)}"
    if options_per_person is not None:
        option_word = "option" if options_per_person == 1 else "options"
        text += f" · Up to {options_per_person} {option_word} per person"
    return text


def limit_message(options_per_person: int) -> str:
    """The message when someone tries to add more options than allowed."""
    option_word = "option" if options_per_person == 1 else "options"
    return f"You can add at most {options_per_person} {option_word} in this room."
