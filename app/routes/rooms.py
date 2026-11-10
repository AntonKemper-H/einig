"""Routes around rooms. For now only the start page exists."""

from flask import Blueprint, render_template

rooms_blueprint = Blueprint("rooms", __name__)


@rooms_blueprint.route("/")
def index() -> str:
    """Show the start page."""
    return render_template("index.html")
