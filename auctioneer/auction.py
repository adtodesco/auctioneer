from datetime import datetime, timedelta

from flask import Blueprint, flash, g, redirect, render_template, request, url_for
from werkzeug.exceptions import abort

from .auth import login_required
from .constants import POSITIONS, TEAMS
from .db import get_db

bp = Blueprint("auction", __name__)

BASE_QUERY = """
SELECT nomination.id,
    nomination.name,
    nomination.position,
    nomination.team,
    nomination.created_at,
    slot.ends_at,
    nomination.nominator_id,
    user_n.username as nominator_username,
    nomination.matcher_id,
    user_m.username as matcher_username,
    nomination.winner_id,
    user_w.username as winner_username,
    bid_w.value as winner_value
FROM nomination
LEFT JOIN slot ON nomination.slot_id = slot.id
LEFT JOIN user user_n ON nomination.nominator_id = user_n.id
LEFT JOIN user user_m ON nomination.matcher_id = user_m.id
LEFT JOIN user user_w ON nomination.winner_id = user_w.id
LEFT JOIN bid bid_w ON nomination.id = bid_w.nomination_id AND nomination.winner_id = bid_w.user_id
ORDER by slot.ends_at DESC
"""

USER_QUERY = """
SELECT nomination.id,
    nomination.name,
    nomination.position,
    nomination.team,
    nomination.created_at,
    slot.ends_at,
    nomination.nominator_id,
    user_n.username as nominator_username,
    nomination.matcher_id,
    user_m.username as matcher_username,
    nomination.winner_id,
    user_w.username as winner_username,
    bid_w.value as winner_value,
    bid_u.value as user_value
FROM nomination
LEFT JOIN slot ON nomination.slot_id = slot.id
LEFT JOIN user user_n ON nomination.nominator_id = user_n.id
LEFT JOIN user user_m ON nomination.matcher_id = user_m.id
LEFT JOIN user user_w ON nomination.winner_id = user_w.id
LEFT JOIN bid bid_w ON nomination.id = bid_w.nomination_id AND nomination.winner_id = bid_w.user_id
LEFT JOIN bid bid_u ON nomination.id = bid_u.nomination_id
WHERE bid_u.user_id = ?
ORDER by slot.ends_at DESC
"""

MINIMUM_BID_VALUE = 10


@bp.route("/")
def index():
    db = get_db()
    if g.user:
        nominations = db.execute(USER_QUERY, (g.user["id"],)).fetchall()
    else:
        nominations = db.execute(BASE_QUERY).fetchall()

    open_nominations = list()
    match_nominations = list()
    closed_nominations = list()
    for nomination in nominations:
        if nomination["winner_id"]:
            closed_nominations.append(nomination)
        elif (
            nomination["ends_at"]
            and nomination["ends_at"] < datetime.utcnow()
            and nomination["matcher_id"]
        ):
            match_nominations.append(nomination)
        else:
            open_nominations.append(nomination)

    return render_template(
        "auction/index.html",
        open_nominations=open_nominations,
        match_nominations=match_nominations,
        closed_nominations=closed_nominations,
    )


@bp.route("/nominate", methods=("GET", "POST"))
@login_required
def nominate():
    if request.method == "POST":
        name = request.form["name"]
        position = request.form["position"]
        team = request.form["team"]
        slot_id = request.form["slot_id"]
        matcher_id = request.form["matcher_id"] or None

        error = None

        if not name:
            error = "Name is required."
        elif not position:
            error = "Position is required."
        elif not team:
            error = "Team is required."
        elif not slot_id:
            error = "Ends at date time is required."

        if error is not None:
            flash(error)
        else:
            db = get_db()
            cur = db.execute(
                "INSERT INTO nomination (name, position, team, slot_id, nominator_id, "
                "matcher_id, winner_id) "
                "VALUES (?, ?, ?, ?, ?, ?, ?) ",
                (
                    name,
                    position,
                    team,
                    slot_id,
                    g.user["id"],
                    matcher_id,
                    None,
                ),
            )
            nomination_id = cur.lastrowid
            users = db.execute("SELECT id FROM user")
            for user in users:
                db.execute(
                    "INSERT INTO bid (user_id, nomination_id, value) Values (?, ?, ?)",
                    (user["id"], nomination_id, None),
                )
            db.commit()
            return redirect(url_for("auction.index"))

    db = get_db()
    users = db.execute("SELECT id, username from user").fetchall()
    slots = get_slots()
    if not slots:
        flash(f"Maximum nominations reached for {g.user['username']}.")

    return render_template(
        "auction/nominate.html",
        teams=TEAMS,
        positions=POSITIONS,
        users=users,
        slots=slots,
    )


@bp.route("/<int:id>/update", methods=("GET", "POST"))
@login_required
def update(id):
    if request.method == "POST":
        name = request.form["name"]
        position = request.form["position"]
        team = request.form["team"]
        slot_id = request.form["slot_id"]
        matcher_id = request.form["matcher_id"] or None
        winner_id = request.form["winner_id"] or None

        error = None

        if not name:
            error = "Name is required."
        elif not position:
            error = "Position is required."
        elif not team:
            error = "Team is required."
        elif not slot_id:
            error = "Ends at date time is required."

        if error is not None:
            flash(error)
        else:
            db = get_db()
            db.execute(
                "UPDATE nomination SET name = ?, position = ?, team = ?, slot_id = ?, "
                "matcher_id = ?, winner_id = ? "
                "WHERE id = ?",
                (name, position, team, slot_id, matcher_id, winner_id, id),
            )
            db.commit()
            return redirect(url_for("auction.index"))

    db = get_db()
    nomination = get_nomination(id)
    users = db.execute("SELECT id, username from user").fetchall()
    slots = get_slots(check_nominator=False)

    return render_template(
        "auction/update.html",
        nomination=nomination,
        positions=POSITIONS,
        teams=TEAMS,
        users=users,
        slots=slots,
    )


@bp.route("/<int:id>/bid", methods=("GET", "POST"))
@login_required
def bid(id):
    nomination = get_nomination(id, check_league_manager=False)
    bid = dict(get_bid(g.user["id"], nomination["id"]))
    if not bid["value"]:
        bid["value"] = ""

    if request.method == "POST":
        value = request.form["value"] or None

        error = None

        if value is not None:
            try:
                int(value)
            except ValueError:
                error = "Bid value must be an integer."
            if int(value) < MINIMUM_BID_VALUE:
                error = f"Minimum bid value is ${MINIMUM_BID_VALUE}."

        if error is not None:
            flash(error)
        else:
            db = get_db()
            db.execute(
                "UPDATE bid SET value = ? WHERE id = ?",
                (value, bid["id"]),
            )
            db.commit()
            return redirect(url_for("auction.index"))

    return render_template("auction/bid.html", nomination=nomination, bid=bid)


@bp.route("/<int:id>/delete", methods=("POST",))
@login_required
def delete(id):
    get_nomination(id)
    db = get_db()
    db.execute("DELETE FROM nomination WHERE id = ?", (id,))
    db.execute("DELETE FROM bid WHERE nomination_id = ?", (id,))
    db.commit()
    return redirect(url_for("auction.index"))


def get_nomination(id, check_league_manager=True):
    nomination = (
        get_db()
        .execute(
            "SELECT n.id, name, position, team, slot_id, nominator_id, matcher_id, "
            "winner_id, created_at, s.ends_at, username FROM nomination n "
            "LEFT JOIN user u ON n.nominator_id = u.id "
            "LEFT JOIN slot s ON n.slot_id = s.id "
            "WHERE n.id = ?",
            (id,),
        )
        .fetchone()
    )

    if nomination is None:
        abort(404, f"Player id {id} doesn't exist.")

    if check_league_manager and g.user["is_league_manager"] is True:
        abort(403)

    return nomination


def get_bid(user_id, nomination_id):
    bid = (
        get_db()
        .execute(
            "SELECT b.id, user_id, nomination_id, value "
            "FROM bid b "
            "WHERE user_id = ? AND nomination_id = ?",
            (user_id, nomination_id),
        )
        .fetchone()
    )

    if bid is None:
        abort(
            404,
            f"Bid for user id {user_id} and nomination id {nomination_id} doesn't "
            f"exist.",
        )

    return bid


def get_slots(
    check_nominator=True,
):
    query_start = (datetime.utcnow() + timedelta(days=2)).strftime(
        "%Y-%m-%d %H:%M:%S"
    )
    query_end = (datetime.utcnow() + timedelta(days=5)).strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    db = get_db()
    slots = db.execute(
        "SELECT slot.id, ends_at FROM slot "
        "LEFT JOIN nomination ON slot.id = nomination.slot_id "
        "WHERE (nomination.slot_id IS NULL OR nomination.slot_id = slot.id) "
        "AND ends_at BETWEEN ? AND ?",
        (query_start, query_end),
    ).fetchall()

    if check_nominator:
        user_nominations = db.execute(
            "SELECT ends_at FROM slot "
            "LEFT JOIN nomination ON slot.id = nomination.slot_id "
            "WHERE nomination.nominator_id = ? AND ends_at BETWEEN ? AND ?",
            (g.user["id"], query_start, query_end),
        ).fetchall()
        user_nomination_dates = [n["ends_at"].date() for n in user_nominations]

        user_slots = list()
        for slot in slots:
            # TODO: Make this check work when all "blocks" are not on the same date
            if slot["ends_at"].date() not in user_nomination_dates:
                user_slots.append(slot)

        slots = user_slots

    return slots
