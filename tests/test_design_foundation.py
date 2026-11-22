"""Tests for D0 – design foundation (specs/d0-design-foundation.md, D21)."""

import re
from pathlib import Path

import pytest

APP_CSS = Path(__file__).resolve().parent.parent / "app" / "static" / "css" / "app.css"
LOGO_IMG = re.compile(r'<img\b[^>]*\bsrc="/static/img/logo\.svg"[^>]*>')
HEADER_LINK = re.compile(r'<a href="/"[^>]*>\s*My rooms\s*</a>')
DESIGN_COLOURS = (
    "--einig-bg",
    "--einig-surface",
    "--einig-button",
    "--einig-text",
    "--einig-muted",
    "--einig-accent",
    "--einig-accent-2",
    "--einig-card",
    "--einig-card-text",
)
SECTION_MARKERS = ("/* D0 foundation */", "/* D1a home, groups, room */", "/* D1b vote, lobby, result */")


# --- Helpers ---------------------------------------------------------------

def create_room(client, title="Dinner", nickname="Anna"):
    response = client.post("/rooms", data={"title": title, "mode": "manual", "nickname": nickname})
    assert response.status_code in (302, 303)
    return response.headers["Location"].rsplit("/rooms/", 1)[1]


def add_option(client, room_id, label):
    assert client.post(f"/rooms/{room_id}/options", data={"label": label}).status_code in (302, 303)


def create_group(client, name="Friday friends", nickname="Anna"):
    response = client.post("/groups", data={"name": name, "nickname": nickname})
    assert response.status_code in (302, 303)
    return response.headers["Location"].rsplit("/groups/", 1)[1]


@pytest.fixture
def pages(client):
    """Paths of every main page, seen by the room's creator."""
    collecting = create_room(client, "Dinner")
    add_option(client, collecting, "Pizza")
    add_option(client, collecting, "Tacos")

    voting = create_room(client, "Movie night")
    add_option(client, voting, "Comedy")
    add_option(client, voting, "Thriller")
    assert client.post(f"/rooms/{voting}/start", data={"time_limit": ""}).status_code in (302, 303)

    closed = create_room(client, "Weekend trip")
    add_option(client, closed, "Lake")
    add_option(client, closed, "Mountains")
    assert client.post(f"/rooms/{closed}/start", data={"time_limit": ""}).status_code in (302, 303)
    assert client.post(f"/rooms/{closed}/close").status_code in (302, 303)

    group = create_group(client)
    return {
        "home": "/",
        "room": f"/rooms/{collecting}",
        "lobby": f"/rooms/{collecting}/lobby",
        "rating page": f"/rooms/{voting}/vote",
        "result": f"/rooms/{closed}/result",
        "group": f"/groups/{group}",
        "new group": "/groups/new",
    }


def css_without_comments():
    return re.sub(r"/\*.*?\*/", "", APP_CSS.read_text(), flags=re.DOTALL)


# --- Logo ------------------------------------------------------------------

def test_every_main_page_shows_the_local_logo_with_alt_text(client, pages):
    for name, path in pages.items():
        response = client.get(path)
        assert response.status_code == 200, name
        html = response.get_data(as_text=True)
        logo = LOGO_IMG.search(html)
        assert logo, f"no logo on the {name} page"
        assert 'alt="Einig"' in logo.group(0), name


def test_the_404_page_shows_the_logo(client):
    response = client.get("/no-such-page")
    assert response.status_code == 404
    assert LOGO_IMG.search(response.get_data(as_text=True))


def test_the_logo_file_is_a_local_svg_without_links_or_scripts(client):
    response = client.get("/static/img/logo.svg")
    assert response.status_code == 200
    assert response.mimetype == "image/svg+xml"
    svg = response.get_data(as_text=True)
    assert "<svg" in svg
    assert "https://" not in svg
    assert "<script" not in svg.lower()


# --- Stylesheet ------------------------------------------------------------

def test_the_design_colours_are_custom_properties_on_root():
    css = css_without_comments()
    root_blocks = re.findall(r":root[^{]*\{([^}]*)\}", css)
    declared = " ".join(root_blocks)
    for name in DESIGN_COLOURS:
        assert re.search(rf"{re.escape(name)}\s*:", declared), f"{name} missing on :root"


def contrast(foreground, background):
    """WCAG 2 contrast ratio of two #RRGGBB colours."""
    def luminance(colour):
        channels = [int(colour[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        linear = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
        return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]
    lighter, darker = sorted((luminance(foreground), luminance(background)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


def test_text_colours_meet_the_contrast_the_spec_promises():
    # Review of #77: the spec promises 4.5:1 for all text; check every text/background pair of D0.
    css = css_without_comments()
    colours = dict(re.findall(r"(--einig-[a-z0-9-]+)\s*:\s*(#[0-9A-Fa-f]{6})\b", css))
    pairs = [
        ("--einig-text", "--einig-bg"),
        ("--einig-muted", "--einig-bg"),
        ("--einig-text", "--einig-button"),
        ("--einig-on-button-muted", "--einig-button"),
        ("--einig-card-text", "--einig-card"),
        ("--einig-card-muted", "--einig-card"),
    ]
    for text, background in pairs:
        assert text in colours and background in colours, (text, background)
        ratio = contrast(colours[text], colours[background])
        assert ratio >= 4.5, f"{text} on {background}: {ratio:.2f}:1"


def test_app_css_has_the_three_section_markers_in_order():
    text = APP_CSS.read_text()
    positions = [text.find(marker) for marker in SECTION_MARKERS]
    assert all(position >= 0 for position in positions), positions
    assert positions == sorted(positions)


# --- Header ----------------------------------------------------------------

def test_the_header_keeps_the_my_rooms_link_on_every_page(client, pages):
    for name, path in pages.items():
        html = client.get(path).get_data(as_text=True)
        header = re.search(r"<header\b.*?</header>", html, flags=re.DOTALL)
        assert header, f"no header on the {name} page"
        assert HEADER_LINK.search(header.group(0)), name
        assert LOGO_IMG.search(header.group(0)), name
