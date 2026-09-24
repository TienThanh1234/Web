"""Register all route modules on the Flask app."""


def register_blueprints(app):
    # Tên hàm giữ nguyên để tương thích với url_for() trong template cũ.
    from routes import auth, characters, items, pages, races, skills, supports, titles

    auth.init_app(app)
    pages.init_app(app)
    characters.init_app(app)
    skills.init_app(app)
    supports.init_app(app)
    items.init_app(app)
    races.init_app(app)
    titles.init_app(app)
