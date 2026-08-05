from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from events_tool.users import get_user, verify_password
from events_tool.web import get_store

bp = Blueprint("auth", __name__)


@bp.route("/login", methods=["GET", "POST"])
def login():
    store = get_store()
    user = get_user(store.conn)

    if user is None:
        return render_template(
            "login.html",
            no_account=True,
            error=None,
        )

    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        if username == user.username and verify_password(user, password):
            session.clear()
            session["user_id"] = user.id
            next_url = request.args.get("next") or url_for("calendar.month_view")
            return redirect(next_url)
        return render_template("login.html", no_account=False, error="Incorrect username or password.")

    return render_template("login.html", no_account=False, error=None)


@bp.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("auth.login"))
