from flask import Blueprint, flash, g, redirect, render_template, request, url_for
from werkzeug.exceptions import abort

from .auth import login_required
from .constants import POSITIONS, TEAMS
from .db import get_db
from .utils import group_slots_by_block, query_range

bp = Blueprint("auction", __name__)

MINIMUM_BID_VALUE = 10
MAX_NOMINATIONS_PER_BLOCK = 2

BASE_QUERY = """
SELECT nomination.id,
    nomination.name,
    nomination.position,
    nomination.team,
    nomination.created_at,
    slot.id as slot_id,
    slot.ends_at,
    slot.block,
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
    slot.id as slot_id,
    slot.ends_at,
    slot.block,
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
            if nomination["matcher_id"]:
                match_nominations.append(nomination)
            else:
                closed_nominations.append(nomination)
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
        bid_value = request.form["bid_value"]

        error = None

        if not name:
            error = "Name is required."
        elif not position:
            error = "Position is required."
        elif not team:
            error = "Team is required."
        elif not slot_id:
            error = "Ends at date time is required."
        elif not bid_value:
            error = "Bid value is required."

        if bid_value is not None:
            try:
                int(bid_value)
            except ValueError:
                error = "Bid value must be an integer."
            if int(bid_value) < MINIMUM_BID_VALUE:
                error = f"Minimum bid value is ${MINIMUM_BID_VALUE}."

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
                user_bid_value = bid_value if user["id"] == g.user["id"] else None
                db.execute(
                    "INSERT INTO bid (user_id, nomination_id, value) VALUES (?, ?, ?)",
                    (user["id"], nomination_id, user_bid_value),
                )
            db.commit()
            return redirect(url_for("auction.index"))

    db = get_db()
    users = db.execute("SELECT id, username from user").fetchall()
    slots = get_open_slots_for_user(days_range=(4, 10))
    if not slots:
        flash(f"No nomination slots currently available for {g.user['username']}.")

    blocks = group_slots_by_block(slots)

    return render_template(
        "auction/nominate.html",
        teams=TEAMS,
        positions=POSITIONS,
        users=users,
        blocks=blocks,
    )


@bp.route("/<int:id>/update", methods=("GET", "POST"))
@login_required
def update(id):
    if not g.user["is_league_manager"]:
        abort(403)

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

    slots = get_open_slots()
    current_slot = db.execute(
        "SELECT id, block, ends_at FROM slot WHERE id = ?", (nomination["slot_id"],)
    ).fetchone()
    slots.append(current_slot)
    blocks = group_slots_by_block(slots)

    return render_template(
        "auction/update.html",
        nomination=nomination,
        positions=POSITIONS,
        teams=TEAMS,
        users=users,
        blocks=blocks,
    )


@bp.route("/<int:id>/bid", methods=("GET", "POST"))
@login_required
def bid(id):
    nomination = get_nomination(id)
    bid = dict(get_bid(g.user["id"], nomination["id"]))
    if not bid["value"]:
        bid["value"] = ""

    if request.method == "POST":
        value = request.form["value"] or None

        error = None

        if value is None and g.user["id"] == nomination["nominator_id"]:
            error = "The nominator cannot reset their bid."

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


@bp.route("/<int:id>/match", methods=("GET", "POST"))
@login_required
def match(id):
    nomination = get_nomination(id)

    if request.method == "POST":
        is_match = request.form["match"] == "yes"

        db = get_db()
        if is_match:
            print("Match!")
        else:
            print("No match!")
        return redirect(url_for("auction.index"))

    return render_template("auction/match.html", nomination=nomination, bid=bid)


@bp.route("/<int:id>/delete", methods=("POST",))
@login_required
def delete(id):
    if not g.user["is_league_manager"]:
        abort(403)

    get_nomination(id)
    db = get_db()
    db.execute("DELETE FROM nomination WHERE id = ?", (id,))
    db.execute("DELETE FROM bid WHERE nomination_id = ?", (id,))
    db.commit()
    return redirect(url_for("auction.index"))


NOMINATION_QUERY = """
SELECT nomination.id,
    nomination.name,
    nomination.position,
    nomination.team,
    nomination.created_at,
    slot.id as slot_id,
    slot.ends_at,
    slot.block,
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
WHERE nomination.id = ?
"""


def get_nomination(id):
    nomination = get_db().execute(NOMINATION_QUERY, (id,)).fetchone()

    if nomination is None:
        abort(404, f"Player id {id} doesn't exist.")

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


def get_open_slots(days_range=None):
    db = get_db()
    if days_range:
        slots = db.execute(
            "SELECT slot.id, block, ends_at FROM slot "
            "LEFT JOIN nomination ON slot.id = nomination.slot_id "
            "WHERE nomination.slot_id IS NULL "
            "AND ends_at BETWEEN ? AND ?",
            (query_range(days_range)),
        ).fetchall()
    else:
        slots = db.execute(
            "SELECT slot.id, block, ends_at FROM slot "
            "LEFT JOIN nomination ON slot.id = nomination.slot_id "
            "WHERE nomination.slot_id IS NULL "
        ).fetchall()

    return slots


def get_open_slots_for_user(days_range=(4, 10)):
    slots = get_open_slots(days_range)

    db = get_db()
    user_nominations = db.execute(
        "SELECT block, COUNT(*) as count FROM slot "
        "LEFT JOIN nomination ON slot.id = nomination.slot_id "
        "WHERE nomination.nominator_id = ? AND ends_at BETWEEN ? AND ? GROUP BY block",
        (g.user["id"], *(query_range(days_range))),
    ).fetchall()

    user_nominations_per_block = {n["block"]: int(n["count"]) for n in user_nominations}

    user_slots = list()
    for slot in slots:
        if user_nominations_per_block.get(slot["block"], 0) < MAX_NOMINATIONS_PER_BLOCK:
            user_slots.append(slot)

    return user_slots
