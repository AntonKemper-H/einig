"""Application factory for the Einig web app."""

import os
import secrets

from dotenv import load_dotenv
from flask import Flask


def create_app(test_config: dict | None = None) -> Flask:
    """Create the Flask application, configure it and register its routes."""
    # Reads a local .env file if there is one, so secrets stay out of the code.
    # On the deployed app the variables come from the host's settings instead.
    load_dotenv()

    app = Flask(__name__)
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "")

    if test_config is not None:
        app.config.update(test_config)

    if not app.config["SECRET_KEY"]:
        # Flask needs a signing key for session cookies. Instead of keeping a
        # default key in the code, make up a throwaway one: the app still runs
        # for a team member who has not filled in .env yet, but every restart
        # invalidates the sessions, which the warning says out loud.
        app.config["SECRET_KEY"] = secrets.token_hex(32)
        app.logger.warning(
            "SECRET_KEY is not set. Using a temporary key, so sessions are lost "
            "on every restart. Set SECRET_KEY in .env or in the host settings."
        )

    from .routes.rooms import rooms_blueprint

    app.register_blueprint(rooms_blueprint)

    return app
