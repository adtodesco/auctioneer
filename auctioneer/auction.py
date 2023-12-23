from datetime import datetime
import pytz

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

from auctioneer.tiebreaker import drop_to_tiebreaker_bottom


from . import db
from .auth import login_required, admin_required
from .constants import POSITIONS, TEAMS
from .model import Bid, Nomination, Player, Slot, User
from .slack import (
    add_auction_match_notification,
    add_auction_won_notification,
    add_player_nominated_notification,
    remove_auction_match_notification,
)
from .utils import (
    get_open_slots,
    get_open_slots_for_user,
    get_user_bid_for_nomination,
    group_slots_by_block,
)

bp = Blueprint("auction", __name__)

MINIMUM_BID_VALUE = 10
MAX_NOMINATIONS_PER_BLOCK = 3
MATCH_TIME_HOURS = 24
NOMINATION_DAY_RANGE = (7, 4)


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
        if row.Nomination.slot.closes_at < datetime.utcnow():
            if row.Nomination.winner_id:
                closed_nominations.append(row)
            elif row.Nomination.matcher_id:
                match_nominations.append(row)
            else:
                open_nominations.append(row)
        else:
            open_nominations.append(row)

    def sort_key(n):
        return n.Nomination.slot.closes_at

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
        flash("No available players remaining.")

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
            if matcher_id:
                add_auction_match_notification(nomination, MATCH_TIME_HOURS)

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


@bp.route("/<int:id>/bid", methods=("GET", "POST"))
@login_required
def bid(id):
    nomination = db.session.get(Nomination, id)
    if nomination is None:
        abort(404, f"Nomination for id {id} doesn't exist.")

    user_bid = get_user_bid_for_nomination(g.user.id, nomination.id)
    if not user_bid.value:
        user_bid.value = ""

    if datetime.utcnow() > nomination.slot.closes_at:
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
            current_app.logger.info(f"Bid {user_bid} updated by {g.user}.")
            return redirect(url_for("auction.index"))

    return render_template("auction/bid.html", nomination=nomination, bid=user_bid)


@bp.route("/<int:id>/match", methods=("GET", "POST"))
@login_required
def match(id):
    nomination = db.session.get(Nomination, id)
    if g.user.id != nomination.matcher_id:
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


@bp.route("/<int:id>/edit", methods=("GET", "POST"))
@login_required
@admin_required
def edit(id):
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
            if nomination.matcher_id and nomination.matcher_id != matcher_id:
                remove_auction_match_notification(nomination)
            nomination.slot_id = slot_id
            nomination.matcher_id = matcher_id
            nomination.winner_id = winner_id
            db.session.add(nomination)
            db.session.commit()
            current_app.logger.info(f"Nomination {nomination} updated by {g.user}.")
            if nomination.matcher_id:
                add_auction_match_notification(nomination, MATCH_TIME_HOURS)
            return redirect(url_for("auction.index"))

    users = db.session.execute(db.select(User)).scalars().all()
    slots = get_open_slots().scalars().all()
    current_slot = db.session.get(Slot, nomination.slot_id)
    slots.append(current_slot)
    blocks = group_slots_by_block(slots)

    for slots in blocks.values():
        convert_slots_timezone(slots)

    return render_template(
        "auction/edit.html",
        nomination=nomination,
        positions=POSITIONS,
        teams=TEAMS,
        users=users,
        blocks=blocks,
    )


@bp.route("/<int:id>/delete", methods=("POST",))
@login_required
@admin_required
def delete(id):
    nomination = db.session.get(Nomination, id)
    if nomination.matcher_id:
        remove_auction_match_notification(nomination)
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

    # TODO: Order by slot.closes_at
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


def close_nomination(nomination):
    winning_bid_value = nomination.bids[0].value
    winning_users = list()
    for bid in nomination.bids:
        if bid.value == winning_bid_value:
            winning_users.append(bid.user)

    if len(winning_users) > 1:
        winning_user = winning_users[0]
        for user in winning_users[1:]:
            if (
                user.tiebreaker_order is not None
                and user.tiebreaker_order < winning_user.tiebreaker_order
            ):
                winning_user = user
        drop_to_tiebreaker_bottom(winning_user)
    else:
        winning_user = winning_users[0]

    nomination.winner_id = winning_user.id
    db.session.add(nomination)
    db.session.commit()


def convert_slots_timezone(slots, timezone="US/Eastern"):
    for slot in slots:
        slot.closes_at = slot.closes_at.replace(tzinfo=pytz.utc).astimezone(
            pytz.timezone(timezone)
        )

    return slots
