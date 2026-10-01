"""Scenario list + detail (URA + Unity CSV)."""
from flask import render_template, abort

from services.auth_service import login_required
from services.scenario_service import (
    get_current_scenarios,
    get_upcoming_scenarios,
    load_scenarios,
)
from services.scenario_guide_service import get_scenario_guide, load_guide_meta, GUIDE_FILES
from services.skill_service import load_skills
from utils import text_to_id


DETAIL_SLUGS = set(GUIDE_FILES.keys())  # ura-finals, unity-cup


SKILL_CANDIDATES = {
    "racing_spirit_speed": ["Racing Spirit: Speed", "racing_spirit_speed"],
    "racing_spirit_stamina": ["Racing Spirit: Stamina", "racing_spirit_stamina"],
    "racing_spirit_power": ["Racing Spirit: Power", "racing_spirit_power"],
    "racing_spirit_wit": ["Racing Spirit: Wit", "racing_spirit_wit"],
    "racing_spirit_guts": ["Racing Spirit: Guts", "racing_spirit_guts"],
    "racing_spirit_mood": ["Racing Spirit: Mood", "racing_spirit_mood"],
    "iron_will": ["Iron Will", "iron_will"],
    "past_my_limits": ["Past My Limits", "past_my_limits"],
    "burning_spirit_spd": ["Burning Spirit SPD", "burning_spirit_spd"],
    "ignited_spirit_spd": ["Ignited Spirit SPD", "ignited_spirit_spd"],
    "burning_spirit_sta": ["Burning Spirit STA", "burning_spirit_sta"],
    "ignited_spirit_sta": ["Ignited Spirit STA", "ignited_spirit_sta"],
    "burning_spirit_pwr": ["Burning Spirit PWR", "burning_spirit_pwr"],
    "ignited_spirit_pwr": ["Ignited Spirit PWR", "ignited_spirit_pwr"],
    "burning_spirit_guts": ["Burning Spirit GUTS", "burning_spirit_guts"],
    "ignited_spirit_guts": ["Ignited Spirit GUTS", "ignited_spirit_guts"],
    "burning_spirit_wit": ["Burning Spirit WIT", "burning_spirit_wit"],
    "ignited_spirit_wit": ["Ignited Spirit WIT", "ignited_spirit_wit"],
    "mile_maven": ["Mile Maven", "mile_maven"],
    "clairvoyance": ["Clairvoyance", "clairvoyance"],
    "indomitable": ["Indomitable", "indomitable"],
    "cooldown": ["Cooldown", "cooldown"],
    "no_stopping_me": ["No Stopping Me!", "No Stopping Me", "no_stopping_me"],
    "its_on": ["It's On!", "Its On!", "its_on"],

    "i_wanna_win_with_you": ["I Wanna Win with You", "i_wanna_win_with_you"],
    "on_the_way_to_our_dream": ["On the Way to Our Dream", "on_the_way_to_our_dream"],
    "full_speed": ["Full Speed!", "Full Speed", "full_speed"],
    "full_tilt": ["Full Tilt", "full_tilt"],
    "concentration": ["Concentration", "concentration"],
    "focus": ["Focus", "focus"],
    "trackblazer": ["Trackblazer", "trackblazer"],
    "rosy_outlook": ["Rosy Outlook", "rosy_outlook"],
    "come_what_may": ["Come What May", "come_what_may"],
    "all_ive_got": ["All I've Got", "All Ive Got", "all_ive_got"],
    "lane_legerdemain": ["Lane Legerdemain", "lane_legerdemain"],
}


def resolve_guide_skill_ids() -> dict:
    found = {k: "" for k in SKILL_CANDIDATES}
    try:
        skills = load_skills()
    except Exception as exc:
        print(f"[scenarios] load_skills: {exc}")
        return found
    by_id, by_name = {}, {}
    for s in skills:
        sid = (s.get("id") or "").strip()
        name = (s.get("name") or "").strip()
        if sid:
            by_id[sid.lower()] = sid
            by_id[text_to_id(sid)] = sid
        if name:
            by_name[name.lower()] = sid
            by_name[text_to_id(name)] = sid
    for key, cands in SKILL_CANDIDATES.items():
        for c in cands:
            cn, cl = text_to_id(c), c.lower()
            if cn in by_id:
                found[key] = by_id[cn]; break
            if cl in by_name:
                found[key] = by_name[cl]; break
            if cn in by_name:
                found[key] = by_name[cn]; break
    return found


def resolve_character_slugs() -> dict:
    wanted = {
        "haru_urara": "haru urara",
        "smart_falcon": "smart falcon",
        "rice_shower": "rice shower",
        "matikanefukukitaru": "matikanefukukitaru",
        "taiki_shuttle": "taiki shuttle",
    }
    found = {k: "" for k in wanted}
    try:
        from services.character_service import load_characters
        chars = load_characters()
    except Exception as exc:
        print(f"[scenarios] load_characters: {exc}")
        return found
    for c in chars:
        name = (c.get("name") or "").strip().lower()
        slug = (c.get("slug") or "").strip()
        if not slug:
            continue
        for key, target in wanted.items():
            if name == target and not found[key]:
                found[key] = slug
    return found


@login_required
def scenario_guide():
    return render_template(
        "scenarios.html",
        current_scenarios=get_current_scenarios(),
        upcoming_scenarios=get_upcoming_scenarios(),
        all_scenarios=load_scenarios(),
        detail_slugs=DETAIL_SLUGS,
    )


@login_required
def scenario_detail(slug):
    slug = (slug or "").strip()
    if slug not in DETAIL_SLUGS and not load_guide_meta(slug):
        abort(404)

    skill_ids = resolve_guide_skill_ids()
    char_slugs = resolve_character_slugs()
    pack = get_scenario_guide(slug, skill_ids=skill_ids, char_slugs=char_slugs)
    if not pack:
        abort(404)

    status_effects = []
    try:
        from services.character_service import load_status_effects
        status_effects = load_status_effects()[0]
    except Exception as exc:
        print(f"[scenarios] load_status_effects: {exc}")
        # fallback: đọc thẳng status_effects.csv nếu có
        try:
            from utils import read_csv_file
            rows = read_csv_file("status_effects.csv")
            for row in rows:
                name = (row.get("name") or "").strip()
                if not name:
                    continue
                status_effects.append({
                    "id": (row.get("id") or "").strip(),
                    "slug": (row.get("slug") or "").strip(),
                    "name": name,
                    "type": (row.get("type") or "neutral").strip().lower() or "neutral",
                    "description": (row.get("description") or "").strip(),
                })
        except Exception as exc2:
            print(f"[scenarios] status_effects.csv: {exc2}")

    return render_template(
        "scenario_detail.html",
        scenario=pack["meta"],
        blocks=pack["blocks"],
        toc=pack["toc"],
        skill_ids=skill_ids,
        char_slugs=char_slugs,
        status_effects=status_effects,
    )


def init_app(app):
    app.add_url_rule("/scenario-guide", "scenario_guide", scenario_guide)
    app.add_url_rule("/scenarios", "scenarios", scenario_guide)
    app.add_url_rule("/scenarios/<slug>", "scenario_detail", scenario_detail)
