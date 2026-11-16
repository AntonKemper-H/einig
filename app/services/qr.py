"""QR code for the invite link (spec: specs/a6-qr-code.md)."""

import segno

QR_TITLE = "QR code to join this room"


def invite_qr_svg(invite_url: str) -> str:
    """Return the invite URL as a QR code in SVG, ready to put straight into the HTML.

    Error level "m" still reads when part of the code is covered or the screen
    reflects. SVG needs no image file and no JavaScript.
    """
    return segno.make(invite_url, error="m").svg_inline(scale=4, title=QR_TITLE)
