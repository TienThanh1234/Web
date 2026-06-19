from flask import Flask, render_template, request, redirect, url_for, session, flash

app = Flask(__name__)
app.secret_key = "Mashkyrielight@!#1234567890"

@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        if username == "admin" and password == "123":
            session["username"] = username
            return redirect(url_for("home"))
        else:
            return render_template("login.html", error="Wrong username or password")

    return render_template("login.html")


@app.route("/home")
def home():
    if "username" not in session:
        return redirect(url_for("login"))

    username = session["username"]
    return render_template("home.html", username=username)


if __name__ == "__main__":
    app.run(debug=True)