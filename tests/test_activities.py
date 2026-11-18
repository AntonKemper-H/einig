"""Tests for C9 – F27 room setup: the activity catalogue and its rules (specs/c9-room-setup.md).

Pure functions only: no app, no database, no Google.
"""

import re

import pytest

from app.services import activities, places, surprise

TYPE_PATTERN = re.compile(r"^[a-z_]+$")


def all_kind_values():
    """Every "activity.kind" value of the catalogue, in catalogue order."""
    return [
        f"{activity}.{kind}"
        for activity, entry in activities.ACTIVITIES.items()
        for kind in entry["kinds"]
    ]


# --- Catalogue ---------------------------------------------------------------

def test_catalogue_is_complete_and_well_formed():
    assert activities.ACTIVITIES
    for activity, entry in activities.ACTIVITIES.items():
        assert entry["label"].strip(), activity
        assert entry["kinds"], activity
        for kind, kind_entry in entry["kinds"].items():
            assert kind_entry["label"].strip(), (activity, kind)
            types = kind_entry["types"]
            assert types, (activity, kind)
            for place_type in types:
                assert TYPE_PATTERN.match(place_type), (activity, kind, place_type)
            assert len(types) == len(set(types)), (activity, kind)


def test_kind_choices_follow_catalogue_order():
    choices = activities.kind_choices()
    expected = [
        (
            entry["label"],
            [(f"{activity}.{kind}", kind_entry["label"]) for kind, kind_entry in entry["kinds"].items()],
        )
        for activity, entry in activities.ACTIVITIES.items()
    ]
    assert choices == expected
    assert choices[0][0] == "Food"
    assert ("food.brunch", "Brunch") in choices[0][1]


# --- parse_kind ----------------------------------------------------------------

def test_parse_kind_accepts_every_catalogue_value():
    for value in all_kind_values():
        activity, kind = value.split(".")
        assert activities.parse_kind(value) == (activity, kind)


@pytest.mark.parametrize(
    "value",
    [None, "", "food", "food.", ".brunch", "food.pizza", "bowling.food", "food.brunch.x"],
)
def test_parse_kind_rejects_values_not_in_catalogue(value):
    assert activities.parse_kind(value) is None


# --- Labels and types ------------------------------------------------------------

def test_kind_label_and_types():
    assert activities.kind_label("food", "brunch") == "Food – Brunch"
    for activity, entry in activities.ACTIVITIES.items():
        for kind, kind_entry in entry["kinds"].items():
            assert activities.kind_types(activity, kind) == kind_entry["types"]


# --- Options per person ------------------------------------------------------------

def test_options_per_person_choices():
    assert activities.OPTIONS_PER_PERSON_CHOICES == [1, 2, 3, 4, 5]


def test_parse_options_per_person_empty_means_unlimited():
    assert activities.parse_options_per_person("") == (None, True)


@pytest.mark.parametrize("number", [1, 2, 3, 4, 5])
def test_parse_options_per_person_accepts_one_to_five(number):
    assert activities.parse_options_per_person(str(number)) == (number, True)


@pytest.mark.parametrize("value", ["0", "6", "-1", "2.5", "abc", None])
def test_parse_options_per_person_rejects_everything_else(value):
    assert activities.parse_options_per_person(value) == (None, False)


def test_validate_setup_accepts_and_rejects():
    cleaned, errors = activities.validate_setup({"kind": "food.brunch", "options_per_person": "3"})
    assert errors == []
    assert cleaned == {"activity": "food", "kind": "brunch", "options_per_person": 3}

    cleaned, errors = activities.validate_setup({"kind": "sport.bowling", "options_per_person": ""})
    assert errors == []
    assert cleaned == {"activity": "sport", "kind": "bowling", "options_per_person": None}

    _, errors = activities.validate_setup({"kind": "food.pizza", "options_per_person": "9"})
    assert errors == [
        "Please choose an activity.",
        "Please choose how many options each person can add.",
    ]


# --- limit_reached -----------------------------------------------------------------

@pytest.mark.parametrize(
    "own_count, limit, expected",
    [
        (0, None, False),
        (50, None, False),
        (0, 1, False),
        (2, 3, False),
        (3, 3, True),
        (4, 3, True),
        (1, 1, True),
    ],
)
def test_limit_reached(own_count, limit, expected):
    assert activities.limit_reached(own_count, limit) is expected


# --- Existing lists stay unchanged --------------------------------------------------

def test_existing_category_lists_are_unchanged():
    assert surprise.SUBCATEGORIES == {
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
    assert places.CATEGORIES == {
        "restaurant": "Restaurant",
        "bar": "Bar",
        "cafe": "Café",
        "movie_theater": "Cinema",
    }
