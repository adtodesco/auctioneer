import functools

from flask import (
    Blueprint,
    flash,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.exceptions import abort
from werkzeug.security import check_password_hash, generate_password_hash

from . import db
from .model import User

bp = Blueprint("auth", __name__, url_prefix="/auth")


@bp.route("/register", methods=("GET", "POST"))
def register():
    unclaimed_teams = (
        db.session.execute(
            db.select(User.team_name)
            .order_by(User.team_name)
            .where(User.username.is_(None))
        )
        .scalars()
        .all()
    )

    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        team = request.form["team"]

        error = None

        if not username:
            error = "Username is required."
        elif not password:
            error = "Password is required."
        elif not team:
            error = "Team is required."

        if error is None:
            user = db.session.execute(
                db.select(User).where(User.team_name == team)
            ).scalar()
            if not user:
                error = "Invalid team."
            else:
                user.username = username
                user.password = generate_password_hash(password)
                db.session.add(user)
                db.session.commit()

                # TODO: This should be able to be removed since all users are created before app start, but keeping
                # commented out for now
                # nominations = db.session.execute(db.select(Nomination))
                # for nomination in nominations.scalars():
                #     nomination.bids.append(
                #         Bid(user_id=user.id, nomination_id=nomination.id, value=None)
                #     )
                # db.session.add_all(nominations)
                # db.session.commit()

                return redirect(url_for("auth.login"))

        flash(error)

    return render_template("auth/register.html", unclaimed_teams=unclaimed_teams)


@bp.route("/login", methods=("GET", "POST"))
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        error = None

        user = db.session.execute(
            db.select(User).where(User.username == username)
        ).scalar()

        if user is None:
            error = "The username you entered has not been registered."
        elif not check_password_hash(user.password, password):
            error = "The password you entered is invalid for this username."

        if error is None:
            session.clear()
            session["user_id"] = user.id
            return redirect(url_for("auction.index"))

        flash(error)

    return render_template("auth/login.html")


@bp.before_app_request
def load_logged_in_user():
    user_id = session.get("user_id")

    if user_id is None:
        g.user = None
    else:
        g.user = db.session.get(User, user_id)


@bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("auction.index"))


def login_required(view):
    @functools.wraps(view)
    def wrapped_view(**kwargs):
        if g.user is None:
            return redirect(url_for("auth.login"))

        return view(**kwargs)

    return wrapped_view


def admin_required(view):
    @functools.wraps(view)
    def wrapped_view(**kwargs):
        if not g.user.is_league_manager:
            abort(403)

        return view(**kwargs)

    return wrapped_view
