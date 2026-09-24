"""Authentication helpers and login_required decorator."""
import csv
import os
from functools import wraps

from flask import redirect, session, url_for
from werkzeug.security import generate_password_hash

from config import USERS_FILE


def login_required(function):
    @wraps(function)
    def wrapper(*args, **kwargs):
        if "username" not in session:
            return redirect(url_for("login"))

        return function(*args, **kwargs)

    return wrapper



def ensure_users_file():
    """Tạo users.csv và tài khoản admin mặc định nếu file chưa tồn tại."""
    if os.path.exists(USERS_FILE):
        return

    with open(USERS_FILE, "w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=["username", "password_hash"]
        )
        writer.writeheader()
        writer.writerow({
            "username": "admin",
            "password_hash": generate_password_hash("123")
        })


def load_users():
    ensure_users_file()
    users = []

    with open(USERS_FILE, newline="", encoding="utf-8-sig") as file:
        reader = csv.DictReader(file)

        for row in reader:
            username = (row.get("username") or "").strip()
            password_hash = (row.get("password_hash") or "").strip()

            if username == "" or password_hash == "":
                continue

            users.append({
                "username": username,
                "password_hash": password_hash
            })

    return users


def find_user(username):
    normalized_username = username.strip().lower()

    for user in load_users():
        if user["username"].lower() == normalized_username:
            return user

    return None


def create_user(username, password):
    ensure_users_file()

    with open(USERS_FILE, "a", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=["username", "password_hash"]
        )
        writer.writerow({
            "username": username,
            "password_hash": generate_password_hash(password)
        })
