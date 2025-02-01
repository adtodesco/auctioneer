from flask import Blueprint, flash, redirect, render_template, request, url_for

from . import db
from .auth import admin_required, login_required
from .model import Player, User

bp = Blueprint("players", __name__, url_prefix="/players")


@bp.route("/")
@login_required
@admin_required
def index():
    players = (
        db.session.execute(db.select(Player).order_by(Player.name)).scalars().all()
    )
    users = db.session.execute(db.select(User)).scalars().all()

    return render_template("players/index.html", players=players, users=users)


@bp.route("/<int:player_id>/edit/", methods=["GET", "POST"])
@login_required
@admin_required
def edit(player_id):
    player = db.session.execute(
        db.select(Player).where(Player.id == player_id)
    ).scalar()
    users = db.session.execute(db.select(User).order_by(User.team_name)).scalars().all()

    if request.method == "POST":
        manager_id = request.form["manager_id"] or None
        matcher_id = request.form["matcher_id"] or None

        print(manager_id, matcher_id)

        error = None

        user_ids = [str(user.id) for user in users]
        if manager_id is not None and manager_id not in user_ids:
            error = "Status is invalid."
        if matcher_id is not None and matcher_id not in user_ids:
            error = "Match rights user ID is invalid."

        if error:
            flash(error)
        else:
            player.manager_id = manager_id
            player.matcher_id = matcher_id
            db.session.commit()
            return redirect(url_for("admin.players.index"))

    return render_template("players/edit.html", player=player, users=users)
