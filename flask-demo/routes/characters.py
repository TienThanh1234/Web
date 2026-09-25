"""Character list and detail routes."""
from flask import render_template

from services.auth_service import login_required
from services.character_service import (
    CHARACTER_TRAINING_EVENT_GROUPS,
    get_character_awakenings,
    get_character_event_skills,
    get_character_innate_skills,
    get_character_objectives,
    get_character_unique_skills,
    load_character_epithets,
    load_character_training_events,
    load_characters,
    load_status_effects,
)


@login_required
def characters():
    character_list = load_characters()
    return render_template("characters.html", characters=character_list)


@login_required
def character_detail(slug):
    character_list = load_characters()

    for character in character_list:
        if character.get("slug", "") == slug:
            return render_template(
                "character_detail.html",
                character=character,
                epithets=load_character_epithets(slug, character),
                unique_skills=get_character_unique_skills(character),
                innate_skills=get_character_innate_skills(character),
                event_skills=get_character_event_skills(character),
                awakenings=get_character_awakenings(character),
                objectives=get_character_objectives(slug, character),
                training_events=load_character_training_events(slug, character),
                training_event_groups=CHARACTER_TRAINING_EVENT_GROUPS,
                status_effects=load_status_effects()[0],
            )

    return "Character not found", 404


def init_app(app):
    app.add_url_rule("/characters", "characters", characters)
    app.add_url_rule("/characters/<slug>", "character_detail", character_detail)
