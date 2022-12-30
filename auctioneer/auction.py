from datetime import datetime

from flask import Blueprint, flash, g, redirect, render_template, request, url_for
from werkzeug.exceptions import abort

from .auth import login_required
from .constants import POSITIONS, TEAMS
from .db import get_db

bp = Blueprint("auction", __name__)

BASE_QUERY = """
SELECT player.id,
    player.name,
    player.position,
    player.team,
    player.created_at,
    player.ends_at,
    player.nominator_id,
    user_n.username as nominator_username,
    player.matcher_id,
    user_m.username as matcher_username,
    player.winner_id,
    user_w.username as winner_username,
    bid_w.value as winner_value
FROM player
LEFT JOIN user user_n ON player.nominator_id = user_n.id
LEFT JOIN user user_m ON player.matcher_id = user_m.id
LEFT JOIN user user_w ON player.winner_id = user_w.id
LEFT JOIN bid bid_w ON player.id = bid_w.player_id AND player.winner_id = bid_w.user_id
ORDER by player.ends_at DESC
"""

USER_QUERY = """
SELECT player.id,
    player.name,
    player.position,
    player.team,
    player.created_at,
    player.ends_at,
    player.nominator_id,
    user_n.username as nominator_username,
    player.matcher_id,
    user_m.username as matcher_username,
    player.winner_id,
    user_w.username as winner_username,
    bid_w.value as winner_value,
    bid_u.value as user_value
FROM player
LEFT JOIN user user_n ON player.nominator_id = user_n.id
LEFT JOIN user user_m ON player.matcher_id = user_m.id
LEFT JOIN user user_w ON player.winner_id = user_w.id
LEFT JOIN bid bid_w ON player.id = bid_w.player_id AND player.winner_id = bid_w.user_id
LEFT JOIN bid bid_u ON player.id = bid_u.player_id
WHERE bid_u.user_id = ?
ORDER by player.ends_at DESC
"""


@bp.route("/")
def index():
    db = get_db()
    if g.user:
        players = db.execute(USER_QUERY, (g.user["id"],)).fetchall()
    else:
        players = db.execute(BASE_QUERY).fetchall()

    open_players = list()
    match_players = list()
    closed_players = list()
    for player in players:
        if player["winner_id"]:
            closed_players.append(player)
        elif player["ends_at"] and player["ends_at"] < datetime.utcnow() and player["matcher_id"]:
            match_players.append(player)
        else:
            open_players.append(player)

    return render_template(
        "auction/index.html",
        open_players=open_players,
        match_players=match_players,
        closed_players=closed_players,
    )


@bp.route("/nominate", methods=("GET", "POST"))
@login_required
def nominate():
    if request.method == "POST":
        name = request.form["name"]
        position = request.form["position"]
        team = request.form["team"]
        matcher_id = request.form["matcher_id"] or None

        error = None

        if not name:
            error = "Name is required."
        elif not position:
            error = "Position is required."
        elif not team:
            error = "Team is required."

        if error is not None:
            flash(error)
        else:
            db = get_db()
            cur = db.execute(
                "INSERT INTO player (name, position, team, ends_at, nominator_id, "
                "matcher_id, winner_id) "
                "VALUES (?, ?, ?, ?, ?, ?, ?) ",
                (
                    name,
                    position,
                    team,
                    None,
                    g.user["id"],
                    matcher_id,
                    None,
                ),
            )
            player_id = cur.lastrowid
            users = db.execute("SELECT id FROM user")
            for user in users:
                db.execute(
                    "INSERT INTO bid (user_id, player_id, value) Values (?, ?, ?)",
                    (user["id"], player_id, None),
                )
            db.commit()
            return redirect(url_for("auction.index"))

    db = get_db()
    users = db.execute("SELECT id, username from user").fetchall()
    return render_template(
        "auction/nominate.html", teams=TEAMS, positions=POSITIONS, users=users
    )


@bp.route("/<int:id>/update", methods=("GET", "POST"))
@login_required
def update(id):
    player = get_player(id)

    if request.method == "POST":
        name = request.form["name"]
        position = request.form["position"]
        team = request.form["team"]
        ends_at = request.form["ends_at"]
        ends_at = None
        # TODO: Add logic to map matcher user to matcher id
        matcher_id = request.form["matcher_id"] or None
        winner_id = request.form["winner_id"] or None

        error = None

        if not name:
            error = "Name is required."
        elif not position:
            error = "Position is required."
        elif not team:
            error = "Team is required."

        if error is not None:
            flash(error)
        else:
            db = get_db()
            db.execute(
                "UPDATE player SET name = ?, position = ?, team = ?, ends_at = ?, "
                "matcher_id = ?, winner_id = ? "
                "WHERE id = ?",
                (name, position, team, ends_at, matcher_id, winner_id, id),
            )
            db.commit()
            return redirect(url_for("auction.index"))

    db = get_db()
    users = db.execute("SELECT id, username from user").fetchall()
    return render_template(
        "auction/update.html",
        player=player,
        positions=POSITIONS,
        teams=TEAMS,
        users=users,
    )


@bp.route("/<int:id>/bid", methods=("GET", "POST"))
@login_required
def bid(id):
    player = get_player(id, check_league_manager=False)
    bid = get_bid(g.user["id"], player["id"])

    if request.method == "POST":
        value = request.form["value"] or None

        error = None
        try:
            int(value)
        except ValueError:
            error = "Bid value must be an integer."

        if error is not None:
            flash(error)
        else:
            db = get_db()
            db.execute(
                "UPDATE bid SET value = ? " "WHERE id = ?",
                (value, bid["id"]),
            )
            db.commit()
            return redirect(url_for("auction.index"))

    return render_template("auction/bid.html", player=player, bid=bid)



@bp.route("/<int:id>/delete", methods=("POST",))
@login_required
def delete(id):
    get_player(id)
    db = get_db()
    db.execute("DELETE FROM player WHERE id = ?", (id,))
    db.execute("DELETE FROM bid WHERE player_id = ?", (id,))
    db.commit()
    return redirect(url_for("auction.index"))


def get_player(id, check_league_manager=True):
    player = (
        get_db()
        .execute(
            "SELECT p.id, name, position, team, nominator_id, matcher_id, "
            "winner_id, created_at, ends_at, username "
            "FROM player p JOIN user u ON p.nominator_id = u.id "
            "WHERE p.id = ?",
            (id,),
        )
        .fetchone()
    )

    if player is None:
        abort(404, f"Player id {id} doesn't exist.")

    if check_league_manager and g.user["is_league_manager"] is True:
        abort(403)

    return player


def get_bid(user_id, player_id):
    bid = (
        get_db()
        .execute(
            "SELECT b.id, user_id, player_id, value "
            "FROM bid b "
            "WHERE user_id = ? AND player_id = ?",
            (user_id, player_id),
        )
        .fetchone()
    )

    if bid is None:
        abort(
            404, f"Bid for user id {user_id} and player id {player_id} doesn't exist."
        )

    return bid
