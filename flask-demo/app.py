"""Flask application entry point."""
from flask import Flask

from config import SECRET_KEY
from routes import register_blueprints
from services.race_service import linkify_race_names


def create_app() -> Flask:
    app = Flask(__name__)
    app.secret_key = SECRET_KEY

    # Jinja filter used in character training event templates
    app.jinja_env.filters["linkify_races"] = linkify_race_names

    register_blueprints(app)
    return app


app = create_app()


if __name__ == "__main__":
    app.run(debug=True)
