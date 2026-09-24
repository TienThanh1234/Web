"""Race list and detail routes."""
from flask import abort, render_template

from services.race_service import load_race_fans, load_race_rewards, load_races


def races():
    race_list = load_races()

    racetracks = sorted({
        race["racetrack"]
        for race in race_list
        if race.get("racetrack") and race["racetrack"] != "Varies"
    })

    return render_template(
        "races.html",
        races=race_list,
        racetracks=racetracks
    )


def race_detail(slug):
    race = next(
        (
            race
            for race in load_races()
            if race.get("slug", "").strip() == slug
        ),
        None
    )

    if race is None:
        abort(404)

    rewards = load_race_rewards(slug)
    fans = load_race_fans(slug)

    return render_template(
        "races_detail.html",
        race=race,
        rewards=rewards,
        fans=fans
    )


def init_app(app):
    app.add_url_rule("/races", "races", races)
    app.add_url_rule("/races/<slug>", "race_detail", race_detail)
