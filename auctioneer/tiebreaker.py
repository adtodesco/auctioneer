from flask import Blueprint, flash, g, redirect, render_template, request, url_for
from werkzeug.exceptions import abort

from .auth import login_required
from .db import get_db

bp = Blueprint("tiebreaker", __name__, url_prefix="/tiebreaker")


@bp.route("/")
def index():
    db = get_db()
    users = db.execute(
        "SELECT id, username, tiebreaker_order FROM user " "ORDER BY tiebreaker_order "
    ).fetchall()

    return render_template("tiebreaker/index.html", users=users)


@bp.route("/edit", methods=("GET", "POST"))
@login_required
def edit():
    if not g.user["is_league_manager"]:
        abort(403)

    db = get_db()
    users = db.execute(
        "SELECT id, username, tiebreaker_order FROM user " "ORDER BY tiebreaker_order "
    ).fetchall()

    if request.method == "POST":
        error = None

        updates = list()
        for user in users:
            name = f"user_{user['id']}_tiebreaker_order"
            if name in request.form:
                tiebreaker_order = request.form[name]
                try:
                    tiebreaker_order = int(tiebreaker_order)
                except ValueError:
                    error = "Tiebreaker order values must be integers."
                    break

                updates.append((tiebreaker_order, user["id"]))

        if len({t[0] for t in updates}) != len(updates):
            error = "Duplicate order values are not allowed."

        if error is not None:
            flash(error)
        else:
            if updates:
                db.executemany(
                    "UPDATE user SET tiebreaker_order = ? WHERE id = ?",
                    updates,
                )
                db.commit()
            return redirect(url_for("tiebreaker.index"))

    return render_template("tiebreaker/edit.html", users=users)
