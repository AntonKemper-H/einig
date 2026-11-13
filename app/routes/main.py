"""General pages: home page and health check."""

from flask import Blueprint, render_template

bp = Blueprint("main", __name__)


@bp.get("/")
def home():
    """Home page with the "create a room" form (F1)."""
    return render_template("home.html")


@bp.get("/health")
def health():
    """Plain 'ok' so the hosting service can check that the app is running."""
    return "ok", 200, {"Content-Type": "text/plain; charset=utf-8"}
