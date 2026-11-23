# E4 – Choose how many places "Places nearby" suggests

Branch: `feature-e4-nearby-place-count`
Tests: `tests/test_nearby_place_count.py`, `tests/test_nearby_place_count_filters.py`

Builds on C2a (search places nearby, `specs/c2-places-search.md`). Asked for after a test on a phone (2026-11-22).

## Why
The search always saves every place Google finds (up to 15). For a small group 15 cards are a lot to rate; the creator should be able to say "just 5".

## What
- The creator's search form in a **"Places nearby"** room gets one more choice: `How many places?` with `5`, `10` and `Up to 15` (`place_count`). `Up to 15` is selected by default, which is today's behaviour.
- The Google request does not change: still one Nearby Search with `maxResultCount` 15 (C2a's test pins it, and Google bills per request, not per place). After the rating and price filters the app keeps **the first N places in Google's order** and saves only those.
- If fewer places are left after the filters, all of them are saved (as today).
- A missing `place_count` means 15 (older forms, C2a's tests). Any other value than 5, 10 or 15 is rejected with `Please choose how many places to suggest.` (status 400, nothing saved, Google not called), and the form is shown again with the entered values.
- **"Surprise me" is not changed:** it keeps its own 5 varied places (C4), and its form has no such choice.
- No schema change, no JavaScript, no new dependency.

Checks (one line = one test), `tests/test_nearby_place_count.py`:
- [ ] The nearby search form has the `place_count` choice with 5, 10 and 15, and 15 is selected by default.
- [ ] The surprise search form has no `place_count` choice.
- [ ] `place_count=5` with 12 places from Google saves exactly the first 5, in Google's order.
- [ ] `place_count=10` with 3 places from Google saves all 3.
- [ ] Without `place_count` up to 15 places are saved, as before.
- [ ] The Google request still asks for 15 results.
- [ ] Rejected: `place_count=7` gives 400 and the message, nothing is saved, Google is not called, and the form keeps the entered values.

Checks added after the review of PR #89 (`tests/test_nearby_place_count_filters.py`; the first file never set a filter together with `place_count`, so cutting Google's raw list before the filters would have passed it):
- [ ] The count is applied after the rating filter: with the first four places rated too low, `place_count=5` and `min_rating=4.5` save the first five places that pass, not the first five Google sent.
- [ ] The same for the price filter (`max_price_level=2`).
- [ ] If fewer places pass the filter than were chosen, all that pass are saved, in Google's order.
