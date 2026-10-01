"""Auth routes: login, register, logout."""
import re

from flask import redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash

from services.auth_service import create_user, find_user


def login():
    if "username" in session:
        return redirect(url_for("home"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        if username == "" or password == "":
            return render_template(
                "login.html",
                error="Please enter both username and password.",
                entered_username=username
            )

        user = find_user(username)

        if user is None or not check_password_hash(
            user["password_hash"],
            password
        ):
            return render_template(
                "login.html",
                error="Wrong username or password.",
                entered_username=username
            )

        session["username"] = user["username"]

        return redirect(url_for("home"))

    return render_template("login.html")


def register():
    if "username" in session:
        return redirect(url_for("home"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not re.fullmatch(r"[A-Za-z0-9_]{3,30}", username):
            return render_template(
                "register.html",
                error=(
                    "Username must be 3-30 characters and contain only "
                    "letters, numbers, or underscores."
                ),
                entered_username=username
            )

        if len(password) < 6:
            return render_template(
                "register.html",
                error="Password must contain at least 6 characters.",
                entered_username=username
            )

        if password != confirm_password:
            return render_template(
                "register.html",
                error="The confirmation password does not match.",
                entered_username=username
            )

        if find_user(username) is not None:
            return render_template(
                "register.html",
                error="This username is already registered.",
                entered_username=username
            )

        create_user(username, password)
        session["username"] = username

        return redirect(url_for("home"))

    return render_template("register.html")


def logout():
    session.clear()
    return redirect(url_for("home"))


def init_app(app):
    app.add_url_rule("/login", "login", login, methods=["GET", "POST"])
    app.add_url_rule("/register", "register", register, methods=["GET", "POST"])
    app.add_url_rule("/logout", "logout", logout)