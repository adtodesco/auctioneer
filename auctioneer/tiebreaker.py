from flask import (
    Blueprint,
    current_app,
    flash,
    g,
    redirect,
    render_template,
    request,
    url_for,
)

from . import db
from .auth import admin_required, login_required
from .model import User

bp = Blueprint("tiebreaker", __name__, url_prefix="/tiebreaker")


@bp.route("/")
def index():
    query = db.select(User).order_by(User.tiebreaker_order)
    users = db.session.execute(query).scalars().all()
    return render_template("tiebreaker/index.html", users=users)


@bp.route("/edit", methods=("GET", "POST"))
@login_required
@admin_required
def edit():
    query = db.select(User).order_by(User.tiebreaker_order)
    users = db.session.execute(query).scalars().all()

    if request.method == "POST":
        error = None

        updates = dict()
        for user in users:
            name = f"user_{user.id}_tiebreaker_order"
            if name in request.form:
                tiebreaker_order = request.form[name]
                try:
                    tiebreaker_order = int(tiebreaker_order)
                    if tiebreaker_order <= 0:
                        raise ValueError()
                except ValueError:
                    error = "Tiebreaker order values must be positive integers."
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
                current_app.logger.info(f"Tiebreaker edited by {g.user}")
                return redirect(url_for("tiebreaker.index"))

        flash(error)

    return render_template("tiebreaker/edit.html", users=users)


def drop_to_tiebreaker_bottom(winning_user):
    users = db.session.execute(db.select(User)).scalars().all()

    updates = dict()
    max_tiebreaker_order = 0
    for user in users:
        if (
            user.tiebreaker_order is not None
            and user.tiebreaker_order > winning_user.tiebreaker_order
        ):
            if user.tiebreaker_order > max_tiebreaker_order:
                max_tiebreaker_order = user.tiebreaker_order
            updates[user.id] = user.tiebreaker_order - 1
            user.tiebreaker_order = None

    if updates:
        updates[winning_user.id] = max_tiebreaker_order
        winning_user.tiebreaker_order = None

        db.session.add_all(users)
        db.session.flush()
        for user_id, tiebreaker_order in updates.items():
            user = db.session.get(User, user_id)
            user.tiebreaker_order = tiebreaker_order
            db.session.add(user)
        db.session.commit()
