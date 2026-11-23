# U2 – Choose *what* first

Branch: `ux-2-what-first`
Tests: `tests/test_u2_what_first.py` (new); twelve reviewed tests changed with the team's OK (list below).
Decision: `docs/decisions.md`, D26. Proposal: issue #95 (Timon).

## Why
Today a new "Surprise me" room shows *What are you planning?* (the setup, C9) and right below *Category* (Restaurant / Bar / Café). Which one counts is not visible, and pressing "Surprise us" first ignores the activity. The app should show what to do, not explain it: pick *what* you want to do first, then the room offers only fitting things.

## What
- **The create form (home page and group page) has an optional activity select** with the same choices as the setup (C9, `name="kind"`, values like `drinks.bar`).
- **With an activity chosen, the room setup is saved right away** with the values the setup form pre-selects: no limit for *Places each person may add*, *Keep everyone's ideas secret until voting* ticked, *Show suggested places to everyone before voting* ticked. The creator can still change the setup while collecting.
- **An empty title is fine once an activity is chosen.** The title then becomes the name of the activity, e.g. `Bar`. Without an activity, `Please enter a title.` stays. An activity that is not in the catalogue is rejected with `Please choose an activity.` and nothing is saved (status 400).
- **The three modes are three big tiles:** ✏️ Own ideas · 📍 Popular nearby · 🎲 Surprise us. Same radio field `mode` and the same values; only the look changes.
- **In a "Places nearby" or "Surprise me" room the search form appears only once a setup is saved.** Until then the setup is open. The select *Category* is gone. The routes `POST /suggest` and `POST /surprise` are not changed: a posted category without a setup still works as before.
- No database change, no new route, no JavaScript.

## Reviewed tests that change (all pinned "the search form with the category select is there before a setup")
They save a setup first (or check the new order). No test is removed.
- `test_room_setup.py`: `test_room_without_setup_is_unchanged[nearby]`, `[surprise]`
- `test_places_search.py`: `test_creator_of_nearby_room_sees_search_form`, `test_no_places_found_shows_message_and_form`, `test_invalid_form_shows_messages_and_values`
- `test_surprise_search.py`: `test_creator_of_surprise_room_sees_surprise_form`, `test_no_places_even_after_widening`, `test_invalid_form`
- `test_place_by_name_route.py`: `test_nearby_search_still_works_after_a_pick`
- `test_nearby_place_count.py`: `test_the_nearby_form_offers_5_10_and_15`, `test_the_surprise_form_has_no_count`, `test_an_invalid_count_is_rejected_and_nothing_changes`
Two of them (`test_invalid_form_shows_messages_and_values`, `test_invalid_form`) keep their category check and now assert that without a setup there is no form to show again; the "form shown again with the entered values" part moves to `tests/test_u2_what_first.py`. Three more only drop the check for the category select.

## Checks (one line = one test), `tests/test_u2_what_first.py`
- [ ] The create form on the home page has the activity select and the three mode tiles; the mode values are unchanged.
- [ ] Creating a room with an activity and no title saves the title `Bar` and the setup (no limit, both choices on).
- [ ] An own title is kept when an activity is chosen.
- [ ] No activity and no title: `Please enter a title.`, status 400, no room saved.
- [ ] An unknown activity: `Please choose an activity.`, status 400, no room saved.
- [ ] A group member planning an activity with an activity and no title gets the same room and setup.
- [ ] A Nearby room without a setup has no search form and no category select; after saving the setup the form is there without the category select.
- [ ] A Surprise room behaves the same.
