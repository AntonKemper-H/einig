"""The 'Room "…" was deleted.' notice fades out by itself (found on a phone, 2026-11-23).

The notice is fixed at the bottom of the screen (F32, D22) and stayed there until the page was
reloaded. Without JavaScript, a CSS animation hides it after a few seconds; the message itself
and its role="status" are unchanged (E3's tests).
"""

import re
from pathlib import Path

APP_CSS = Path(__file__).resolve().parent.parent / "app" / "static" / "css" / "app.css"


def css():
    return re.sub(r"/\*.*?\*/", "", APP_CSS.read_text(), flags=re.DOTALL)


def rules_for(selector):
    return [body for sel, body in re.findall(r"([^{}]+)\{([^{}]*)\}", css()) if sel.strip() == selector]


def keyframes(name):
    match = re.search(rf"@keyframes\s+{re.escape(name)}\s*\{{(.*?)\}}\s*\}}", css(), flags=re.DOTALL)
    return match.group(1) if match else None


def test_the_notice_runs_an_animation_that_stays_at_its_end():
    body = " ".join(rules_for(".home-notice"))
    animation = re.search(r"animation\s*:\s*([^;]+);", body)
    assert animation, ".home-notice has no animation"
    parts = animation.group(1).split()
    assert "forwards" in parts or "both" in parts, "the notice would come back after the animation"
    assert any(re.fullmatch(r"\d+(\.\d+)?s", part) for part in parts)


def test_the_animation_hides_the_notice_completely():
    body = " ".join(rules_for(".home-notice"))
    name = re.search(r"animation\s*:\s*([\w-]+)", body).group(1)
    frames = keyframes(name)
    assert frames, f"@keyframes {name} missing"
    assert re.search(r"visibility\s*:\s*hidden", frames)
    assert re.search(r"opacity\s*:\s*0\b", frames)
