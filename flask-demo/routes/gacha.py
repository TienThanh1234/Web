"""Gacha pages."""
from flask import redirect, render_template, request, url_for

from services.auth_service import login_required
from services.gacha_service import (
    filter_banners,
    format_banner_period,
    get_current_banners,
    get_history_index,
    get_special_banners,
)


@login_required
def gacha():
    current = get_current_banners()
    for b in current:
        b["period_label"] = format_banner_period(b)
    return render_template(
        "gacha.html",
        current_banners=current,
        history_links=get_history_index(),
        has_special=bool(get_special_banners()),
    )


@login_required
def gacha_special():
    banners = get_special_banners()
    for b in banners:
        b["period_label"] = format_banner_period(b)
    return render_template(
        "gacha_history.html",
        page_title="Special banners",
        heading="Special banners",
        year="all",
        banner_type="special",
        banners=banners,
        filter_year="all",
        filter_type="all",
    )


@login_required
def gacha_history(year=None, banner_type=None):
    # /gacha/history?year=2025&type=character
    # /gacha/history/2025/character
    q_year = request.args.get("year") or year or "all"
    q_type = request.args.get("type") or banner_type or "all"

    banners = filter_banners(year=q_year, banner_type=q_type, server="global")
    for b in banners:
        b["period_label"] = format_banner_period(b)

    type_label = {
        "character": "characters",
        "characters": "characters",
        "support": "supports",
        "supports": "supports",
        "all": "all banners",
    }.get((q_type or "all").lower(), q_type)

    year_label = "All years" if str(q_year).lower() == "all" else str(q_year)

    return render_template(
        "gacha_history.html",
        page_title=f"Gacha History — Global · {year_label} · {type_label}",
        heading="Gacha Banner History",
        year=q_year,
        banner_type=q_type,
        banners=banners,
        filter_year=str(q_year),
        filter_type=(q_type or "all").lower(),
    )


def init_app(app):
    app.add_url_rule("/gacha", "gacha", gacha)
    app.add_url_rule("/gacha/special", "gacha_special", gacha_special)
    app.add_url_rule("/gacha/history", "gacha_history", gacha_history)
    app.add_url_rule(
        "/gacha/history/<year>/<banner_type>",
        "gacha_history_path",
        gacha_history,
    )
