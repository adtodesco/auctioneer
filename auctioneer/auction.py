from datetime import datetime

from flask import (
    Blueprint,
    Response,
    current_app,
    flash,
    g,
    redirect,
    render_template,
    request,
    url_for,
)
from werkzeug.exceptions import abort

from . import db
from .auth import login_required
from .constants import POSITIONS, TEAMS
from .model import Bid, Nomination, Player, Slot, User
from .slack import add_auction_won_notification, add_player_nominated_notification
from .utils import (
    close_nomination,
    convert_slots_timezone,
    get_open_slots,
    get_open_slots_for_user,
    get_user_bid_for_nomination,
    group_slots_by_block,
)

bp = Blueprint("auction", __name__)

MINIMUM_BID_VALUE = 10
MAX_NOMINATIONS_PER_BLOCK = 2
MATCH_TIME_HOURS = 24
NOMINATION_DAY_RANGE = (1, 5)


@bp.route("/")
def index():
    if g.user:
        statement = db.select(Nomination, Bid).join(Bid).where(Bid.user_id == g.user.id)
    else:
        statement = db.select(Nomination)
    result = db.session.execute(statement)

    open_nominations = list()
    match_nominations = list()
    closed_nominations = list()

    for row in result:
        if row.Nomination.slot.ends_at < datetime.utcnow():
            if row.Nomination.winner_id:
                closed_nominations.append(row)
            elif row.Nomination.matcher_id:
                match_nominations.append(row)
            else:
                open_nominations.append(row)
        else:
            open_nominations.append(row)

    def sort_key(n):
        return n.Nomination.slot.ends_at

    open_nominations = sorted(open_nominations, key=sort_key, reverse=True)
    match_nominations = sorted(match_nominations, key=sort_key, reverse=True)
    closed_nominations = sorted(closed_nominations, key=sort_key, reverse=True)

    return render_template(
        "auction/index.html",
        open_nominations=open_nominations,
        match_nominations=match_nominations,
        closed_nominations=closed_nominations,
    )


@bp.route("/nominate", methods=("GET", "POST"))
@login_required
def nominate():
    users = db.session.execute(db.select(User)).scalars().all()

    statement = (
        db.select(Player)
        .where(~db.exists().where(Nomination.player_id == Player.id))
        .order_by(Player.name)
    )
    players = db.session.execute(statement).scalars().all()
    if not players:
        flash(f"No available players remaining.")

    slots = get_open_slots_for_user(
        g.user.id,
        day_range=NOMINATION_DAY_RANGE,
        max_nominations_per_block=MAX_NOMINATIONS_PER_BLOCK,
    )
    if not slots:
        flash(f"No nomination slots currently available for {g.user.username}.")

    blocks = group_slots_by_block(slots)

    if request.method == "POST":
        player_id = request.form["player_id"]
        slot_id = request.form["slot_id"]
        matcher_id = request.form["matcher_id"] or None
        bid_value = request.form["bid_value"]

        error = None

        if not player_id:
            error = "Player is required."
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
            nomination = Nomination(
                player_id=player_id,
                slot_id=slot_id,
                nominator_id=g.user.id,
                matcher_id=matcher_id,
                winner_id=None,
            )
            for user in users:
                user_bid_value = bid_value if user.id == g.user.id else None
                user.bids.append(Bid(nomination=nomination, value=user_bid_value))

            db.session.add(nomination)
            db.session.add_all(users)
            db.session.commit()

            current_app.logger.info(
                f"Nomination {nomination} created by {nomination.nominator_user}."
            )

            add_player_nominated_notification(nomination)

            return redirect(url_for("auction.index"))

    for slots in blocks.values():
        convert_slots_timezone(slots)

    return render_template(
        "auction/nominate.html",
        teams=TEAMS,
        positions=POSITIONS,
        users=users,
        players=players,
        blocks=blocks,
    )


@bp.route("/<int:id>/update", methods=("GET", "POST"))
@login_required
def update(id):
    if not g.user.is_league_manager:
        abort(403)

    nomination = db.session.get(Nomination, id)
    if nomination is None:
        abort(404, f"Nomination for id {id} doesn't exist.")

    if request.method == "POST":
        slot_id = request.form["slot_id"]
        matcher_id = request.form["matcher_id"] or None
        winner_id = request.form["winner_id"] or None

        error = None

        if not slot_id:
            error = "Ends at date time is required."

        if error is not None:
            flash(error)
        else:
            nomination.slot_id = slot_id
            nomination.matcher_id = matcher_id
            nomination.winner_id = winner_id
            db.session.add(nomination)
            db.session.commit()
            current_app.logger.info(f"Nomination {nomination} updated by {g.user}.")
            return redirect(url_for("auction.index"))

    users = db.session.execute(db.select(User)).scalars().all()
    slots = get_open_slots().scalars().all()
    current_slot = db.session.get(Slot, nomination.slot_id)
    slots.append(current_slot)
    blocks = group_slots_by_block(slots)

    for slots in blocks.values():
        convert_slots_timezone(slots)

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
    nomination = db.session.get(Nomination, id)
    if nomination is None:
        abort(404, f"Nomination for id {id} doesn't exist.")

    user_bid = get_user_bid_for_nomination(g.user.id, nomination.id)
    if not user_bid.value:
        user_bid.value = ""

    if datetime.utcnow() > nomination.slot.ends_at:
        flash("Auction has closed.")
    elif request.method == "POST":
        value = request.form["value"] or None

        error = None

        if value is None and g.user.id == nomination.nominator_id:
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
            user_bid.value = value
            db.session.add(user_bid)
            db.session.commit()
            current_app.logger.info(f"Bid {bid} updated by {g.user}.")
            return redirect(url_for("auction.index"))

    return render_template("auction/bid.html", nomination=nomination, bid=user_bid)


@bp.route("/<int:id>/match", methods=("GET", "POST"))
@login_required
def match(id):
    nomination = db.session.get(Nomination, id)
    if g.user.id != nomination.nominator_id:
        abort(403)

    if request.method == "POST":
        is_match = request.form["match"] == "yes"
        if is_match:
            user_bid = get_user_bid_for_nomination(g.user.id, nomination.id)
            user_bid.value = nomination.bids[0].value
            nomination.winner_id = g.user.id
            db.session.add(user_bid)
            db.session.add(nomination)
            db.session.commit()
            current_app.logger.info(
                f"Match for nomination {nomination} accepted by {g.user}."
            )
        else:
            close_nomination(nomination)
            current_app.logger.info(
                f"Match for nomination {nomination} declined by {g.user}."
            )

        add_auction_won_notification(nomination)

        return redirect(url_for("auction.index"))

    return render_template("auction/match.html", nomination=nomination, bid=bid)


@bp.route("/<int:id>/delete", methods=("POST",))
@login_required
def delete(id):
    if not g.user.is_league_manager:
        abort(403)

    nomination = db.session.get(Nomination, id)
    nomination_str = str(nomination)
    db.session.delete(nomination)
    db.session.commit()
    current_app.logger.info(f"Nomination {nomination_str} deleted by {g.user}.")
    return redirect(url_for("auction.index"))


@bp.route("/results")
@login_required
def results():
    def generate(headers, rows):
        yield ",".join(headers) + "\n"
        for row in rows:
            yield ",".join(row) + "\n"

    nominations = db.session.execute(
        db.select(Nomination).where(Nomination.winner_id.is_not(None))
    )
    results_headers = ["Fantrax ID", "Player", "Position", "Team", "Winner", "Bids"]
    results_rows = [
        [
            nomination.player.fantrax_id,
            nomination.player.name,
            nomination.player.position,
            nomination.player.team,
            nomination.winner_user.username,
            ";".join([str(b.value) for b in nomination.bids]),
        ]
        for nomination in nominations.scalars()
    ]
    current_app.logger.info(f"Results downloaded by {g.user}.")

    return Response(
        generate(results_headers, results_rows),
        mimetype="text/csv",
    )
