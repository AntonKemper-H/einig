"""Tests for C10 – F30 place details, part 1: field masks and reading Google's answer
(specs/c10-place-details.md).

These tests never call Google: `requests.get` is replaced by a fake, and the
root conftest.py makes any other real request fail.

What the tests pin about the new data (the spec leaves the exact shape to the tests):
- `details["kind"]` is a string, `details["rating_count"]` a non-negative int.
- `details["back"]` is a dict with exactly the keys `description` (text or None),
  `offers` (text like "Dinner · Wine" or None), `reviews` (list of review dicts) and
  `photos` (list of photo dicts). It exists only for `BACK_FIELD_MASK` and only if
  Google sent at least one of the four parts.
- A review dict has exactly the keys `stars_text`, `age`, `text`, `author_name`,
  `author_uri`, `author_photo_uri`, `google_maps_uri`.
- A photo dict has exactly the keys `photo_name`, `photo_author`, `photo_author_uri`.
"""

import pytest

from app.services import places
from app.services.places import (
    BACK_FIELD_MASK,
    CARD_FIELD_MASK,
    DETAILS_FIELD_MASK,
    MAX_EXTRA_PHOTOS,
    MAX_REVIEWS_SHOWN,
    build_card,
    get_place_details,
    load_cards,
)

FAKE_KEY = "fake-key-for-tests-0123456789"
DETAILS_URL = "https://places.googleapis.com/v1/places/"
OLD_FIELD_MASK = "displayName,rating,priceLevel,location,photos"
FALLBACK_NAME = "Place from Google Maps"

OLD_DETAIL_KEYS = {
    "name", "rating", "price_level", "latitude", "longitude",
    "photo_name", "photo_author", "photo_author_uri",
}
OLD_CARD_KEYS = {
    "source", "name", "photo_name", "photo_author", "photo_author_uri",
    "rating_text", "price_text", "distance_text", "details_missing",
}
BACK_KEYS = {"description", "offers", "reviews", "photos"}
REVIEW_KEYS = {
    "stars_text", "age", "text", "author_name", "author_uri", "author_photo_uri", "google_maps_uri",
}
PHOTO_KEYS = {"photo_name", "photo_author", "photo_author_uri"}


# --- Fake Google -----------------------------------------------------------

class FakeResponse:
    def __init__(self, status_code=200, body=None):
        self.status_code = status_code
        self.body = {} if body is None else body
        self.content = b""
        self.headers = {"Content-Type": "application/json"}
        self.text = str(self.body)

    def json(self):
        return self.body


class FakeGet:
    """Replaces requests.get: answers by URL and records every call with its keyword arguments."""

    def __init__(self):
        self.responses = {}
        self.calls = []

    def __call__(self, url, **kwargs):
        self.calls.append({"url": url, **kwargs})
        return self.responses.get(url, FakeResponse(status_code=404, body={"error": {}}))


@pytest.fixture
def fake_get(monkeypatch):
    fake = FakeGet()
    monkeypatch.setattr(places.requests, "get", fake)
    return fake


def photo(place_id, number, author="Maria Silva"):
    return {
        "name": f"places/{place_id}/photos/ref-{number}",
        "authorAttributions": [{"displayName": author, "uri": f"https://maps.google.com/{author.split()[0].lower()}"}],
    }


def review(number, **changes):
    body = {
        "name": f"places/place-a/reviews/review-{number}",
        "relativePublishTimeDescription": f"{number} weeks ago",
        "rating": 5,
        "text": {"text": f"Review text {number}", "languageCode": "en"},
        "authorAttribution": {
            "displayName": f"Author {number}",
            "uri": f"https://www.google.com/maps/contrib/{number}",
            "photoUri": f"https://lh3.googleusercontent.com/a/{number}",
        },
        "googleMapsUri": f"https://www.google.com/maps/reviews/{number}",
    }
    body.update(changes)
    return body


def full_back_answer(place_id="place-a"):
    """An answer with every field of BACK_FIELD_MASK."""
    return {
        "displayName": {"text": "Pizza Roma", "languageCode": "en"},
        "rating": 4.5,
        "userRatingCount": 812,
        "priceLevel": "PRICE_LEVEL_MODERATE",
        "location": {"latitude": 38.740, "longitude": -9.153},
        "primaryTypeDisplayName": {"text": "Italian Restaurant", "languageCode": "en"},
        "editorialSummary": {"text": "Wood-fired pizza near the river.", "languageCode": "en"},
        "servesDinner": True,
        "servesBrunch": False,
        "reviews": [review(1), review(2), review(3), review(4)],
        "photos": [photo(place_id, number) for number in range(1, 7)],
    }


def answer(fake_get, place_id, body):
    fake_get.responses[DETAILS_URL + place_id] = FakeResponse(body=body)


def back_of(fake_get, body, place_id="place-a"):
    """The `back` part of get_place_details with BACK_FIELD_MASK for this answer (None if absent)."""
    answer(fake_get, place_id, body)
    return get_place_details(FAKE_KEY, place_id, BACK_FIELD_MASK).get("back")


def is_empty_back(back):
    """True for 'no back key' and for a back whose four parts are all empty."""
    return not back or not any(back.values())


def google_option(place_id="place-a", option_id=1):
    return {"id": option_id, "source": "google", "place_id": place_id, "label": None}


# --- The three field masks ---------------------------------------------------

def test_field_masks_are_built_from_each_other_and_never_use_a_star():
    assert DETAILS_FIELD_MASK == OLD_FIELD_MASK
    assert CARD_FIELD_MASK == OLD_FIELD_MASK + ",userRatingCount,primaryTypeDisplayName"
    assert BACK_FIELD_MASK.startswith(CARD_FIELD_MASK + ",")
    back_fields = BACK_FIELD_MASK[len(CARD_FIELD_MASK) + 1:].split(",")
    assert back_fields == [
        "editorialSummary", "reviews",
        "servesBreakfast", "servesBrunch", "servesLunch", "servesDinner", "servesVegetarianFood",
        "servesCoffee", "servesDessert", "servesBeer", "servesWine", "servesCocktails",
        "goodForGroups", "outdoorSeating", "reservable",
    ]
    for mask in (DETAILS_FIELD_MASK, CARD_FIELD_MASK, BACK_FIELD_MASK):
        assert "*" not in mask


def test_limits():
    assert MAX_REVIEWS_SHOWN == 3
    assert MAX_EXTRA_PHOTOS == 3


# --- get_place_details: the request ------------------------------------------

def test_default_mask_sends_exactly_the_old_request(fake_get):
    answer(fake_get, "place-a", full_back_answer())
    get_place_details(FAKE_KEY, "place-a")
    assert len(fake_get.calls) == 1
    call = fake_get.calls[0]
    assert call["url"] == DETAILS_URL + "place-a"
    assert call["timeout"] == 5
    assert call["headers"] == {"X-Goog-Api-Key": FAKE_KEY, "X-Goog-FieldMask": OLD_FIELD_MASK}
    assert "params" not in call


@pytest.mark.parametrize("mask", [CARD_FIELD_MASK, BACK_FIELD_MASK], ids=["card", "back"])
def test_card_and_back_masks_send_the_mask_and_the_language(fake_get, mask):
    answer(fake_get, "place-a", full_back_answer())
    get_place_details(FAKE_KEY, "place-a", mask)
    assert len(fake_get.calls) == 1
    call = fake_get.calls[0]
    assert call["url"] == DETAILS_URL + "place-a"
    assert call["timeout"] == 5
    assert call["headers"] == {"X-Goog-Api-Key": FAKE_KEY, "X-Goog-FieldMask": mask}
    assert call["params"] == {"languageCode": "en"}


# --- read_details: kind and rating count ---------------------------------------

def test_answer_without_the_new_fields_gives_exactly_todays_keys(fake_get):
    body = full_back_answer()
    for field in ("userRatingCount", "primaryTypeDisplayName", "editorialSummary", "reviews", "servesDinner"):
        del body[field]
    answer(fake_get, "place-a", body)
    for mask in (DETAILS_FIELD_MASK, CARD_FIELD_MASK, BACK_FIELD_MASK):
        details = get_place_details(FAKE_KEY, "place-a", mask)
        assert set(details) - {"back"} == OLD_DETAIL_KEYS
    # The default call (old mask) never has a back, even though Google sent two photos.
    assert set(get_place_details(FAKE_KEY, "place-a")) == OLD_DETAIL_KEYS


def test_kind_and_rating_count_are_added_when_google_sent_them(fake_get):
    answer(fake_get, "place-a", full_back_answer())
    details = get_place_details(FAKE_KEY, "place-a", CARD_FIELD_MASK)
    assert details["kind"] == "Italian Restaurant"
    assert details["rating_count"] == 812
    assert details["name"] == "Pizza Roma"
    assert "back" not in details  # the card mask never builds a back


@pytest.mark.parametrize("count", ["812", -3, True, 812.5, None, [812]])
def test_wrongly_typed_or_negative_count_is_left_out(fake_get, count):
    body = full_back_answer()
    body["userRatingCount"] = count
    answer(fake_get, "place-a", body)
    details = get_place_details(FAKE_KEY, "place-a", CARD_FIELD_MASK)
    assert "rating_count" not in details
    assert details["kind"] == "Italian Restaurant"


@pytest.mark.parametrize("kind", ["Italian Restaurant", {"languageCode": "en"}, {"text": ""}, {"text": 5}, None])
def test_wrongly_typed_or_empty_kind_is_left_out(fake_get, kind):
    body = full_back_answer()
    body["primaryTypeDisplayName"] = kind
    answer(fake_get, "place-a", body)
    details = get_place_details(FAKE_KEY, "place-a", CARD_FIELD_MASK)
    assert "kind" not in details
    assert details["rating_count"] == 812


# --- build_card ----------------------------------------------------------------

def card_for(details):
    return build_card(google_option(), details, 38.737, -9.153)


def old_details(**changes):
    details = {
        "name": "Pizza Roma", "rating": 4.5, "price_level": 2, "latitude": 38.740, "longitude": -9.153,
        "photo_name": "places/place-a/photos/ref-1", "photo_author": None, "photo_author_uri": None,
    }
    details.update(changes)
    return details


def test_build_card_with_a_count_shows_it_and_passes_the_kind_on():
    card = card_for(old_details(rating_count=812, kind="Italian Restaurant"))
    assert card["rating_text"] == "4.5 ★ (812)"
    assert card["kind"] == "Italian Restaurant"


def test_build_card_without_the_new_fields_is_exactly_todays_card():
    card = card_for(old_details())
    assert set(card) == OLD_CARD_KEYS
    assert card["rating_text"] == "4.5 ★"
    assert card["price_text"] == "€€"


def test_build_card_adds_kind_only_when_present():
    assert "kind" not in card_for(old_details(rating_count=812))
    assert "kind" in card_for(old_details(kind="Bar"))


def test_build_card_passes_the_back_on_only_when_present():
    back = {"description": "Nice.", "offers": None, "reviews": [], "photos": []}
    assert card_for(old_details(back=back))["back"] == back
    assert "back" not in card_for(old_details())


def test_a_card_without_details_has_no_new_keys():
    card = card_for(None)
    assert set(card) == OLD_CARD_KEYS
    assert card["name"] == FALLBACK_NAME


# --- The back: description ---------------------------------------------------------

def test_description_comes_from_the_editorial_summary(fake_get):
    back = back_of(fake_get, full_back_answer())
    assert set(back) == BACK_KEYS
    assert back["description"] == "Wood-fired pizza near the river."


@pytest.mark.parametrize("summary", [None, "text", {"languageCode": "en"}, {"text": ""}, {"text": 5}])
def test_without_a_usable_summary_there_is_no_description(fake_get, summary):
    body = full_back_answer()
    body["editorialSummary"] = summary
    assert back_of(fake_get, body)["description"] is None


def test_missing_summary_gives_no_description(fake_get):
    body = full_back_answer()
    del body["editorialSummary"]
    assert back_of(fake_get, body)["description"] is None


# --- The back: offers ----------------------------------------------------------------

def test_offers_contain_only_true_fields_in_the_fixed_order(fake_get):
    # Deliberately not in the fixed order, with false, wrongly typed and missing fields.
    body = full_back_answer()
    body.update({
        "reservable": True, "servesWine": True, "servesBreakfast": True, "outdoorSeating": True,
        "servesVegetarianFood": True, "goodForGroups": True, "servesDinner": True,
        "servesBrunch": False, "servesLunch": "yes", "servesCoffee": 1, "servesBeer": None,
    })
    back = back_of(fake_get, body)
    assert back["offers"] == (
        "Breakfast · Dinner · Vegetarian · Wine · Good for groups · Outdoor seating · Reservations"
    )


def test_all_offers_have_their_label(fake_get):
    body = full_back_answer()
    flags = {
        "servesBreakfast": "Breakfast", "servesBrunch": "Brunch", "servesLunch": "Lunch",
        "servesDinner": "Dinner", "servesVegetarianFood": "Vegetarian", "servesCoffee": "Coffee",
        "servesDessert": "Dessert", "servesBeer": "Beer", "servesWine": "Wine",
        "servesCocktails": "Cocktails", "goodForGroups": "Good for groups",
        "outdoorSeating": "Outdoor seating", "reservable": "Reservations",
    }
    body.update({field: True for field in flags})
    assert back_of(fake_get, body)["offers"] == " · ".join(flags.values())


def test_no_true_field_means_no_offers(fake_get):
    body = full_back_answer()
    body.update({"servesDinner": False, "servesBrunch": False})
    assert back_of(fake_get, body)["offers"] is None


# --- The back: reviews --------------------------------------------------------------

def test_at_most_three_reviews_in_googles_order_with_every_part(fake_get):
    back = back_of(fake_get, full_back_answer())
    assert len(back["reviews"]) == 3
    assert back["reviews"][0] == {
        "stars_text": "5 ★",
        "age": "1 weeks ago",
        "text": "Review text 1",
        "author_name": "Author 1",
        "author_uri": "https://www.google.com/maps/contrib/1",
        "author_photo_uri": "https://lh3.googleusercontent.com/a/1",
        "google_maps_uri": "https://www.google.com/maps/reviews/1",
    }
    assert [item["text"] for item in back["reviews"]] == ["Review text 1", "Review text 2", "Review text 3"]
    assert all(set(item) == REVIEW_KEYS for item in back["reviews"])


def test_review_text_is_not_shortened_or_changed(fake_get):
    long_text = "Line one.\n\nLine two " + "very " * 400 + "long. <b>Tags</b> & more."
    body = full_back_answer()
    body["reviews"] = [review(1, text={"text": long_text, "languageCode": "en"})]
    assert back_of(fake_get, body)["reviews"][0]["text"] == long_text


def test_a_review_without_text_or_without_author_name_is_skipped(fake_get):
    body = full_back_answer()
    body["reviews"] = [
        review(1, text={"text": "", "languageCode": "en"}),
        review(2, text=None),
        review(3, authorAttribution={"uri": "https://www.google.com/maps/contrib/3"}),
        review(4, authorAttribution={"displayName": "", "uri": "https://www.google.com/maps/contrib/4"}),
        review(5),
    ]
    assert [item["text"] for item in back_of(fake_get, body)["reviews"]] == ["Review text 5"]


def test_skipped_reviews_do_not_count_towards_the_limit(fake_get):
    body = full_back_answer()
    body["reviews"] = [review(1, text=None)] + [review(number) for number in range(2, 7)]
    assert [item["text"] for item in back_of(fake_get, body)["reviews"]] == [
        "Review text 2", "Review text 3", "Review text 4",
    ]


@pytest.mark.parametrize(
    "field_path, key",
    [
        (("authorAttribution", "uri"), "author_uri"),
        (("authorAttribution", "photoUri"), "author_photo_uri"),
        (("googleMapsUri",), "google_maps_uri"),
    ],
)
@pytest.mark.parametrize("bad_uri", ["javascript:alert(1)", "http://example.com/x", "//example.com/x", "", 5, None])
def test_a_link_that_is_not_https_is_dropped_and_the_rest_kept(fake_get, field_path, key, bad_uri):
    body = full_back_answer()
    item = review(1)
    target = item
    for step in field_path[:-1]:
        target = target[step]
    target[field_path[-1]] = bad_uri
    body["reviews"] = [item]
    shown = back_of(fake_get, body)["reviews"][0]
    assert shown[key] is None
    assert shown["text"] == "Review text 1"
    assert shown["author_name"] == "Author 1"
    others = {"author_uri", "author_photo_uri", "google_maps_uri"} - {key}
    assert all(shown[other] is not None for other in others)


def test_stars_and_age_are_optional(fake_get):
    body = full_back_answer()
    body["reviews"] = [review(1, rating="five", relativePublishTimeDescription=None)]
    shown = back_of(fake_get, body)["reviews"][0]
    assert shown["stars_text"] == ""
    assert shown["age"] == ""
    assert shown["text"] == "Review text 1"


# --- The back: more photos -----------------------------------------------------------

def test_extra_photos_are_the_second_to_fourth_with_their_authors(fake_get):
    back = back_of(fake_get, full_back_answer())
    assert len(back["photos"]) == 3
    assert [item["photo_name"] for item in back["photos"]] == [
        "places/place-a/photos/ref-2", "places/place-a/photos/ref-3", "places/place-a/photos/ref-4",
    ]
    assert back["photos"][0] == {
        "photo_name": "places/place-a/photos/ref-2",
        "photo_author": "Maria Silva",
        "photo_author_uri": "https://maps.google.com/maria",
    }
    assert all(set(item) == PHOTO_KEYS for item in back["photos"])


def test_a_photo_of_another_place_or_with_a_wrong_name_is_skipped(fake_get):
    body = full_back_answer()
    body["photos"] = [
        photo("place-a", 1),
        photo("other-place", 2),
        {"name": "places/place-a/photos/ref with spaces"},
        {"name": "https://evil.example/photo.jpg"},
        {"name": 5},
        "not a dict",
        photo("place-a", 7),
        photo("place-a", 8),
    ]
    assert [item["photo_name"] for item in back_of(fake_get, body)["photos"]] == [
        "places/place-a/photos/ref-7", "places/place-a/photos/ref-8",
    ]


def test_extra_photo_author_link_must_be_https(fake_get):
    body = full_back_answer()
    body["photos"][1]["authorAttributions"][0]["uri"] = "javascript:alert(1)"
    second = back_of(fake_get, body)["photos"][0]
    assert second["photo_author_uri"] is None
    assert second["photo_author"] == "Maria Silva"


def test_with_only_one_photo_there_are_no_extra_photos(fake_get):
    body = full_back_answer()
    body["photos"] = [photo("place-a", 1)]
    assert back_of(fake_get, body)["photos"] == []


# --- The back: damaged answers -----------------------------------------------------------

DAMAGED_ANSWERS = [
    {"editorialSummary": 5, "reviews": "x", "photos": "x", "servesDinner": "yes", "goodForGroups": [1]},
    {"editorialSummary": [], "reviews": [1, None, "x", {}, {"authorAttribution": 5, "text": 5}], "photos": [None, 5, []]},
    {"editorialSummary": {"text": None}, "reviews": {"a": 1}, "photos": {"a": 1}, "reservable": {}},
    {"reviews": [{"text": {"text": "ok"}, "authorAttribution": "Anna"}], "photos": [{"name": None}]},
]


@pytest.mark.parametrize("body", DAMAGED_ANSWERS)
def test_a_damaged_answer_gives_no_back_or_an_empty_back_and_never_raises(fake_get, body):
    assert is_empty_back(back_of(fake_get, body))


def test_an_answer_without_any_back_field_gives_no_back_or_an_empty_one(fake_get):
    assert is_empty_back(back_of(fake_get, {"displayName": {"text": "Pizza Roma"}}))


# --- load_cards ---------------------------------------------------------------------------

def masks_used(fake_get):
    return {call["url"]: call["headers"]["X-Goog-FieldMask"] for call in fake_get.calls}


def test_load_cards_uses_the_card_mask_for_every_card_and_the_back_mask_only_for_back_for(fake_get):
    for place_id in ("place-a", "place-b", "place-c"):
        answer(fake_get, place_id, full_back_answer(place_id))
    options = [google_option("place-a", 1), google_option("place-b", 2), google_option("place-c", 3)]
    cards = load_cards(FAKE_KEY, options, 38.737, -9.153, back_for={"place-b"})
    assert len(fake_get.calls) == 3  # still one call per Google option
    assert masks_used(fake_get) == {
        DETAILS_URL + "place-a": CARD_FIELD_MASK,
        DETAILS_URL + "place-b": BACK_FIELD_MASK,
        DETAILS_URL + "place-c": CARD_FIELD_MASK,
    }
    assert [card["rating_text"] for card in cards] == ["4.5 ★ (812)"] * 3
    assert [card["kind"] for card in cards] == ["Italian Restaurant"] * 3
    assert ["back" in card for card in cards] == [False, True, False]


@pytest.mark.parametrize("back_for", [None, set()])
def test_load_cards_without_back_for_never_asks_for_the_back(fake_get, back_for):
    answer(fake_get, "place-a", full_back_answer())
    cards = load_cards(FAKE_KEY, [google_option("place-a")], 38.737, -9.153, back_for=back_for)
    assert masks_used(fake_get) == {DETAILS_URL + "place-a": CARD_FIELD_MASK}
    assert "back" not in cards[0]


def test_load_cards_still_works_with_the_old_call(fake_get):
    answer(fake_get, "place-a", full_back_answer())
    cards = load_cards(FAKE_KEY, [google_option("place-a")], 38.737, -9.153)
    assert cards[0]["name"] == "Pizza Roma"
    assert len(fake_get.calls) == 1


def test_load_cards_manual_options_make_no_call(fake_get):
    manual = {"id": 9, "source": "manual", "place_id": None, "label": "Cinema"}
    cards = load_cards(FAKE_KEY, [manual], None, None, back_for={"place-a"})
    assert fake_get.calls == []
    assert cards == [{"source": "manual", "label": "Cinema"}]


def test_load_winner_is_unchanged_and_never_asks_for_the_back(fake_get):
    """load_winner (C3) loads its card through load_cards: card mask, no back, one call."""
    answer(fake_get, "place-a", full_back_answer())
    result = places.load_winner(FAKE_KEY, None, google_option("place-a"))
    assert masks_used(fake_get) == {DETAILS_URL + "place-a": CARD_FIELD_MASK}
    assert "back" not in result["card"]
    assert result["card"]["kind"] == "Italian Restaurant"
