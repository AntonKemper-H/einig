"""Einig – Flask application factory.

`create_app()` builds and configures the app. Tests call it with their own
config; the real app reads its settings from environment variables.
"""

import os

from dotenv import load_dotenv
from flask import Flask, render_template

from app import db
from app.routes import main


def create_app(test_config: dict | None = None) -> Flask:
    """Create the Flask app, either from a test config or from environment variables."""
    app = Flask(__name__, instance_relative_config=True)

    if test_config is None:
        # Real run: read .env locally (on the host, variables are set in its settings).
        load_dotenv()
        app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY")
        app.config["DATABASE"] = os.path.join(app.instance_path, "einig.sqlite")
    else:
        # Tests: use exactly what the test passes in, ignore the environment.
        app.config.update(test_config)

    # The secret key signs the session cookie that identifies participants.
    # A hard-coded fallback would let anyone forge sessions, so we refuse to start.
    if not app.config.get("SECRET_KEY"):
        raise RuntimeError(
            "SECRET_KEY is not set. Copy .env.example to .env and fill it in "
            "(or set it in the hosting settings)."
        )

    os.makedirs(app.instance_path, exist_ok=True)

    db.init_app(app)
    app.register_blueprint(main.bp)

    @app.errorhandler(404)
    def page_not_found(error):
        """Show a friendly page for unknown URLs instead of the default error."""
        return render_template("404.html"), 404

    return app
