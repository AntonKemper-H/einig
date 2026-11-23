"""Tests for E6 – clearer messages when "Use my location" fails (specs/e6-location-messages.md).

The script runs in the browser, so these tests read its source (like the swipe script's
tests). The real error codes are checked by hand on a phone or iPad after deploying.
"""

import re
from pathlib import Path

JS_FOLDER = Path(__file__).parent.parent / "app" / "static" / "js"
GEOLOCATION_JS = JS_FOLDER / "geolocation.js"

BLOCKED_MESSAGE = (
    "Location is blocked. Allow it for this site in your browser. On iPhone or iPad: "
    "Settings → Privacy & Security → Location Services → Safari Websites."
)
NOT_FOUND_MESSAGE = "Your location could not be found. Please try again."
TOO_SLOW_MESSAGE = "Finding your location took too long. Please try again."
OTHER_MESSAGE = "Location not shared. Please allow location access and try again."


def source():
    """The script without comments, so a message only mentioned in a comment does not count."""
    text = GEOLOCATION_JS.read_text(encoding="utf-8")
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    return re.sub(r"(?m)^\s*//.*$|(?<=\s)//\s.*$", "", text)


def branch_for_code(code):
    """The statements that run for one error code: from `case <code>` or `== <code>` to the next one."""
    text = source()
    pattern = rf"(?:case\s+{code}\s*:|===?\s*{code}\b|\b{code}\s*===?)(.*?)(?=case\s+\d\s*:|===?\s*\d\b|\b\d\s*===?|default\s*:|else\b|$)"
    match = re.search(pattern, text, flags=re.DOTALL)
    assert match, f"no branch for error code {code}"
    return match.group(1)


def test_error_callback_reads_the_error_code():
    text = source()
    assert re.search(r"function\s*\(\s*error\s*\)", text)
    assert "error.code" in text


def test_code_1_says_location_is_blocked_with_the_ios_path():
    assert BLOCKED_MESSAGE in branch_for_code(1)
    assert "Location Services" in BLOCKED_MESSAGE and "Safari Websites" in BLOCKED_MESSAGE


def test_code_2_says_location_could_not_be_found():
    assert NOT_FOUND_MESSAGE in branch_for_code(2)


def test_code_3_says_it_took_too_long():
    assert TOO_SLOW_MESSAGE in branch_for_code(3)


def test_the_three_messages_are_different():
    assert len({BLOCKED_MESSAGE, NOT_FOUND_MESSAGE, TOO_SLOW_MESSAGE}) == 3
    text = source()
    for message in (BLOCKED_MESSAGE, NOT_FOUND_MESSAGE, TOO_SLOW_MESSAGE):
        assert text.count(message) == 1


def test_other_codes_keep_the_old_generic_message():
    assert OTHER_MESSAGE in source()
    # It is the fallback, so it is not part of any of the three branches.
    for code in (1, 2, 3):
        assert OTHER_MESSAGE not in branch_for_code(code)


def test_other_messages_are_unchanged():
    text = source()
    assert "Your browser cannot share its location." in text
    assert "Getting your location …" in text
    assert "Location shared. You can now search." in text


def test_rounding_and_options_are_unchanged():
    text = source()
    assert "Math.round(value * 1000) / 1000" in text
    assert "{ enableHighAccuracy: false, timeout: 10000, maximumAge: 60000 }" in text


def test_no_new_javascript_file_was_added():
    names = {path.name for path in JS_FOLDER.glob("*.js")}
    assert names == {"geolocation.js", "swipe.js", "invite.js"}  # U3 (D28): invite.js, approved with the team in issue #95
