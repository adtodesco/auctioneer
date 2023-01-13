from flask import Blueprint, flash, g, redirect, render_template, request, url_for
from werkzeug.exceptions import abort

from . import db
from .auth import login_required
from .model import User

bp = Blueprint("tiebreaker", __name__, url_prefix="/tiebreaker")


@bp.route("/")
def index():
    users = (
        db.session.execute(db.select(User).order_by(User.tiebreaker_order))
        .scalars()
        .all()
    )
    return render_template("tiebreaker/index.html", users=users)


@bp.route("/edit", methods=("GET", "POST"))
@login_required
def edit():
    if not g.user.is_league_manager:
        abort(403)

    users = (
        db.session.execute(db.select(User).order_by(User.tiebreaker_order))
        .scalars()
        .all()
    )

    if request.method == "POST":
        error = None

        updates = dict()
        for user in users:
            name = f"user_{user.id}_tiebreaker_order"
            if name in request.form:
                tiebreaker_order = request.form[name]
                try:
                    tiebreaker_order = int(tiebreaker_order)
                except ValueError:
                    error = "Tiebreaker order values must be integers."
                    break

                if tiebreaker_order != user.tiebreaker_order:
                    user.tiebreaker_order = None
                    updates[user.id] = tiebreaker_order

        if error is None and updates:
            db.session.add_all(users)
            db.session.flush()
            for user_id, tiebreaker_order in updates.items():
                user = db.session.get(User, user_id)
                user.tiebreaker_order = tiebreaker_order
                db.session.add(user)
            try:
                db.session.commit()
            except db.exc.IntegrityError:
                db.session.rollback()
                error = "Tiebreaker order values must be unique."
            else:
                return redirect(url_for("tiebreaker.index"))

        flash(error)

    return render_template("tiebreaker/edit.html", users=users)
