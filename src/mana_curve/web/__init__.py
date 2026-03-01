"""Flask web application for mana_curve simulations."""

from __future__ import annotations

from flask import Flask


def create_app() -> Flask:
    """Application factory."""
    app = Flask(
        __name__,
        template_folder="templates",
        static_folder="static",
    )
    app.config["SECRET_KEY"] = "mana-curve-dev-key"

    from .routes import register_blueprints

    register_blueprints(app)

    return app
