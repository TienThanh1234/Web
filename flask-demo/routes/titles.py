"""Trainer titles route."""
from flask import render_template

from services.auth_service import login_required
from services.title_service import load_titles


@login_required
def titles():
    return render_template("titles.html", titles=load_titles())


def init_app(app):
    app.add_url_rule("/titles", "titles", titles)
