"""Character Profile list + detail."""
from flask import render_template, abort

from services.auth_service import login_required
from services.profile_service import get_profile, load_profiles_index


@login_required
def profiles():
    profile_list = load_profiles_index()
    profiles = [
        {
            "name": p["name"],
            "slug": p["slug"],
            "image": p.get("image") or "face.png",
        }
        for p in profile_list
    ]
    return render_template(
        "profiles.html",
        profiles=profiles,
        profile_count=len(profiles),
    )


@login_required
def profile_detail(slug):
    profile = get_profile(slug)
    if profile is None:
        abort(404)
    return render_template("profile_detail.html", profile=profile)


def init_app(app):
    app.add_url_rule("/profiles", "profiles", profiles)
    app.add_url_rule("/profiles/<slug>", "profile_detail", profile_detail)