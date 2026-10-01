"""Skill list and detail routes."""
from flask import abort, render_template

from services.auth_service import login_required
from services.skill_service import get_skill_detail, group_skills_by_category


@login_required
def skills():
    categories, grouped_skills = group_skills_by_category()

    return render_template(
        "skills.html",
        categories=categories,
        grouped_skills=grouped_skills
    )


@login_required
def skill_detail(skill_id):
    skill = get_skill_detail(skill_id)

    if skill is None:
        abort(404)

    return render_template("skill_detail.html", skill=skill)


def init_app(app):
    app.add_url_rule("/skills", "skills", skills)
    app.add_url_rule("/skills/<skill_id>", "skill_detail", skill_detail)
