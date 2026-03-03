"""Flask web application for auto_goldfish simulations."""

from __future__ import annotations

import os

from flask import Flask


def create_app() -> Flask:
    """Application factory."""
    app = Flask(
        __name__,
        template_folder="templates",
        static_folder="static",
    )
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "auto-goldfish-dev-key")

    from .routes import register_blueprints

    register_blueprints(app)

    return app
