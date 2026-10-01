"""Support card routes."""
from flask import abort, current_app, render_template

from services.auth_service import login_required
from services.skill_service import get_skills_by_ids
from services.support_service import (
    get_support_card_by_id,
    load_support_card_effects,
    load_support_card_training_events,
    load_support_cards,
)


@login_required
def support_card():
    try:
        support_cards = load_support_cards()

        return render_template(
            "support_card.html",
            support_cards=support_cards
        )

    except Exception:
        current_app.logger.exception(
            "Không thể tải danh sách Support Card từ Supabase."
        )

        return render_template(
            "support_card.html",
            support_cards=[],
            load_error=(
                "Không thể tải dữ liệu Support Card từ Supabase. "
                "Hãy kiểm tra bảng, key và RLS policy."
            )
        ), 500


@login_required
def support_detail(card_id):
    try:
        card = get_support_card_by_id(card_id)

        if card is None:
            abort(404)

        effects = load_support_card_effects(card_id)

        (
            date_events,
            chain_events,
            random_events,
            special_events
        ) = load_support_card_training_events(card_id)

        hint_skills = get_skills_by_ids(
            card.get("hint_skill_ids", ""),
            card.get("highlight_skill_ids", "")
        )

        event_skills = get_skills_by_ids(
            card.get("event_skill_ids", ""),
            card.get("highlight_skill_ids", "")
        )

        stat_gain_list = []
        stat_gain_text = card.get("stat_gain", "")

        if stat_gain_text.strip() != "":
            stat_gain_list = stat_gain_text.split("|")

        return render_template(
            "support_card_details.html",
            card=card,
            effects=effects,
            hint_skills=hint_skills,
            event_skills=event_skills,
            stat_gain_list=stat_gain_list,
            chain_events=chain_events,
            random_events=random_events,
            date_events=date_events,
            special_events=special_events
        )

    except Exception as error:
        if getattr(error, "code", None) == 404:
            raise

        current_app.logger.exception(
            "Không thể tải chi tiết Support Card %s từ Supabase.",
            card_id
        )

        return (
            "Không thể tải chi tiết Support Card từ Supabase. "
            "Hãy kiểm tra bảng, dữ liệu khóa ngoại và RLS policy.",
            500
        )


def init_app(app):
    app.add_url_rule("/support-card", "support_card", support_card)
    app.add_url_rule("/supports", "supports", support_card)
    app.add_url_rule("/support-card/<card_id>", "support_detail", support_detail)
    # alias path — same view, different endpoint name for Flask uniqueness
    app.add_url_rule("/supports/<card_id>", "support_detail_alias", support_detail)
