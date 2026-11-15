"""Einig – Flask application factory.

`create_app()` builds and configures the app. Tests call it with their own
config; the real app reads its settings from environment variables.
"""

import os

from dotenv import load_dotenv
from flask import Flask, render_template
from werkzeug.middleware.proxy_fix import ProxyFix

from app import db
from app.routes import main, pwa, rooms


def create_app(test_config: dict | None = None) -> Flask:
    """Create the Flask app, either from a test config or from environment variables."""
    app = Flask(__name__, instance_relative_config=True)

    if test_config is None:
        # Real run: read .env locally (on the host, variables are set in its settings).
        load_dotenv()
        app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY")
        # Server-only key for the Places API. May be empty: then the app still works with
        # manual options and shows a friendly message instead of searching (C2a).
        app.config["GOOGLE_MAPS_API_KEY"] = os.environ.get("GOOGLE_MAPS_API_KEY", "").strip()
        # Browser key for the winner's map (Maps Embed API, C3), restricted to our domain.
        # May be empty: then the result page shows the route link without a map.
        app.config["GOOGLE_MAPS_EMBED_KEY"] = os.environ.get("GOOGLE_MAPS_EMBED_KEY", "").strip()
        # Deployed: hosted Postgres from the secret DATABASE_URL (Render's disk is wiped on
        # every restart). Locally the variable is empty, so a SQLite file is used instead.
        database_url = os.environ.get("DATABASE_URL", "").strip()
        if database_url:
            app.config["DATABASE_URL"] = database_url
        else:
            app.config["DATABASE"] = os.path.join(app.instance_path, "einig.sqlite")
        # Only Render's settings turn this on (C1b). Off by default, so the local server is unaffected.
        trust_value = os.environ.get("TRUST_PROXY_HEADERS", "").strip().lower()
        app.config["TRUST_PROXY_HEADERS"] = trust_value in ("1", "true")
    else:
        # Tests: use exactly what the test passes in, ignore the environment.
        app.config.update(test_config)

    # Catch a wrong value early. The message never repeats the URL: it contains the password.
    database_url = app.config.get("DATABASE_URL")
    if database_url and not database_url.startswith(("postgresql://", "postgres://")):
        raise RuntimeError(
            "DATABASE_URL must start with postgresql:// or postgres://. "
            "Check the value in the hosting settings."
        )

    # The secret key signs the session cookie that identifies participants.
    # A hard-coded fallback would let anyone forge sessions, so we refuse to start.
    if not app.config.get("SECRET_KEY"):
        raise RuntimeError(
            "SECRET_KEY is not set. Copy .env.example to .env and fill it in "
            "(or set it in the hosting settings)."
        )

    # Render ends HTTPS at its proxy and talks plain http to the app. ProxyFix reads the
    # scheme from the proxy's X-Forwarded-Proto header, so the invite link starts with
    # https. Only that header is trusted: Render sets it, while it passes on client values
    # in X-Forwarded-For, and the Host header is already correct (review of PR #21).
    # Without a proxy in front, any client could send the header itself, hence the switch.
    if app.config.get("TRUST_PROXY_HEADERS"):
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=0, x_proto=1, x_host=0)

    os.makedirs(app.instance_path, exist_ok=True)

    db.init_app(app)
    app.register_blueprint(main.bp)
    app.register_blueprint(rooms.bp)
    app.register_blueprint(pwa.bp)

    @app.errorhandler(404)
    def page_not_found(error):
        """Show a friendly page for unknown URLs instead of the default error."""
        return render_template("404.html"), 404

    return app
