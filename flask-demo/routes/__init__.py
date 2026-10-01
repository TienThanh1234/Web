"""Register all route modules on the Flask app."""


def register_blueprints(app):
    from routes import (
        auth,
        characters,
        profiles,
        gacha,
        items,
        pages,
        races,
        scenarios,
        skills,
        supports,
        titles,
    )

    auth.init_app(app)
    pages.init_app(app)
    characters.init_app(app)
    profiles.init_app(app)
    skills.init_app(app)
    supports.init_app(app)
    items.init_app(app)
    races.init_app(app)
    titles.init_app(app)
    gacha.init_app(app)
    scenarios.init_app(app)  # /scenario-guide + /scenarios/<slug>
