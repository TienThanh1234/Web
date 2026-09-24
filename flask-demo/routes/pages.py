"""Home and static guide pages."""
from flask import render_template, session

from services.auth_service import login_required


def home():
    return render_template(
        "home.html",
        username=session.get("username")
    )


@login_required
def banner_history():
    return render_template("banner_history.html")


@login_required
def cm_guide():
    return render_template("cm_guide.html")


@login_required
def scenario_guide():
    return render_template("scenario_guide.html")


def init_app(app):
    app.add_url_rule("/", "home", home)
    app.add_url_rule("/home", "home_alt", home)
    app.add_url_rule("/banner-history", "banner_history", banner_history)
    app.add_url_rule("/cm-guide", "cm_guide", cm_guide)
    app.add_url_rule("/scenario-guide", "scenario_guide", scenario_guide)
