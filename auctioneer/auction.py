import math
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
from .audit_log import (
    log_admin_player_sign,
    log_bid,
    log_match_decision,
    log_nomination,
    log_nomination_edit,
    log_player_signed,
)
from .auth import admin_required, login_required
from .config import get_match_time_hours, get_minimum_bid_value, get_minimum_total_salary, get_salary_cap
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
    get_user_bid_for_nomination,
    group_slots_by_round,
    user_can_nominate,
)

bp = Blueprint("auction", __name__)


def get_contract_options_by_year(minimum_total_salary):
    """Convert MINIMUM_TOTAL_SALARY indices (1-10) to calendar years.

    Returns a dict mapping calendar years to minimum salary requirements.
    For example: {2026: 12, 2027: 30, 2028: 60, ...}
    """
    if not minimum_total_salary:
        return {}

    salary_cap = get_salary_cap()
    if not salary_cap:
        return {}

    base_year = min(salary_cap.keys())

    # Convert indices to calendar years
    result = {}
    for contract_length, min_salary in minimum_total_salary.items():
        end_year = base_year + contract_length - 1
        result[end_year] = min_salary

    return result


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
        if row.Nomination.player.manager_id:
            closed_nominations.append(row)
        elif (
            row.Nomination.slot.closes_at < datetime.utcnow()
            and row.Nomination.player.matcher_id
        ):
            match_nominations.append(row)
        else:
            open_nominations.append(row)

    def sort_key(n):
        return n.Nomination.slot.closes_at

    open_nominations = sorted(open_nominations, key=sort_key)
    match_nominations = sorted(match_nominations, key=sort_key)
    closed_nominations = sorted(closed_nominations, key=sort_key)

    return render_template(
        "auction/index.html",
        open_nominations=open_nominations,
        match_nominations=match_nominations,
        closed_nominations=closed_nominations,
    )


@bp.route("/nominate/", methods=["GET", "POST"])
@login_required
def nominate():
    users = db.session.execute(db.select(User)).scalars().all()

    statement = (
        db.select(Player)
        .where(Player.manager_id.is_(None))
        .where(~db.exists().where(Nomination.player_id == Player.id))
        .order_by(Player.name)
    )
    players = db.session.execute(statement).scalars().all()
    if not players:
        flash("No available players remaining to nominate.")

    no_slots_message = (
        "Nominations are unavailable because we are outside of the nomination periods or we have reached the max number"
        " of nominations for this round."
    )
    max_nominations_reached_message = "Nominations are unavailable because you have reached the max number of nominations for this round."

    slots = get_open_slots(in_nomination_period_only=True)
    if not slots:
        flash(no_slots_message)

    if request.method == "POST":
        player_id = request.form["player_id"]
        bid_value = request.form["bid_value"]

        error = None

        if not slots:
            error = no_slots_message
        elif not user_can_nominate(g.user, slots[0]):
            error = max_nominations_reached_message
        elif not player_id:
            error = "Player is required."
        elif not bid_value:
            error = "Bid value is required."

        if bid_value is not None:
            try:
                int(bid_value)
            except ValueError:
                error = "Bid value must be an integer."
            minimum_bid = get_minimum_bid_value()
            if int(bid_value) < minimum_bid:
                error = f"Minimum bid value is ${minimum_bid}."

        if error is not None:
            current_app.logger.error(
                f"User {g.user} could not nominate player because of error: {error}"
            )
            flash(error)
        else:
            slot_id = slots[0].id
            nomination = Nomination(
                player_id=player_id,
                slot_id=slot_id,
                nominator_id=g.user.id,
            )
            for user in users:
                user_bid_value = bid_value if user.id == g.user.id else None
                user.bids.append(Bid(nomination=nomination, value=user_bid_value))

            db.session.add(nomination)
            db.session.add_all(users)

            # Log audit event
            log_nomination(nomination, g.user)

            db.session.commit()

            current_app.logger.info(f"User {g.user} created nomination {nomination}")

            add_player_nominated_notification(nomination)
            if nomination.player.matcher_id:
                add_auction_match_notification(nomination, get_match_time_hours())

            return redirect(url_for("auction.index"))

    # Calculate reference table for minimum contracts
    minimum_total_salary = get_contract_options_by_year(get_minimum_total_salary())
    min_contracts = {}
    if minimum_total_salary:
        last_year = list(minimum_total_salary)[0] - 1
        for year, min_salary in minimum_total_salary.items():
            min_contracts[year] = {
                'total': min_salary,
                'annual': math.ceil(min_salary / (year - last_year))
            }

    return render_template(
        "auction/nominate.html",
        teams=TEAMS,
        positions=POSITIONS,
        users=users,
        players=players,
        min_contracts=min_contracts,
    )


@bp.route("/<int:nomination_id>/bid/", methods=["GET", "POST"])
@login_required
def bid(nomination_id):
    nomination = db.session.get(Nomination, nomination_id)
    if nomination is None:
        abort(404, f"Nomination for id {nomination_id} doesn't exist.")

    user_bid = get_user_bid_for_nomination(g.user.id, nomination.id)
    if not user_bid.value:
        user_bid.value = ""

    if datetime.utcnow() > nomination.slot.closes_at:
        flash("Auction has closed.")
    elif request.method == "POST":
        value = request.form["value"] or None
        action = request.form["action"]

        if action.lower() == "reset":
            value = None

        error = None

        if value is None and g.user.id == nomination.nominator_id:
            error = "The nominator cannot reset their bid."

        if value is not None:
            try:
                int(value)
            except ValueError:
                error = "Bid value must be an integer."
            minimum_bid = get_minimum_bid_value()
            if int(value) < minimum_bid:
                error = f"Minimum bid value is ${minimum_bid}."

        if error is not None:
            current_app.logger.error(
                f"User {g.user} could not bid on nomination {nomination} because of error: {error}"
            )
            flash(error)
        else:
            old_value = user_bid.value if user_bid.value != "" else None
            user_bid.value = value
            db.session.add(user_bid)

            # Log audit event (sensitive)
            log_bid(nomination, g.user, old_value, value)

            db.session.commit()
            current_app.logger.info(
                f"User {g.user} updated bid on nomination {nomination}"
            )
            return redirect(url_for("auction.index"))

    # Calculate reference table for minimum contracts
    minimum_total_salary = get_contract_options_by_year(get_minimum_total_salary())
    min_contracts = {}
    if minimum_total_salary:
        last_year = list(minimum_total_salary)[0] - 1
        for year, min_salary in minimum_total_salary.items():
            min_contracts[year] = {
                'total': min_salary,
                'annual': math.ceil(min_salary / (year - last_year))
            }

    return render_template("auction/bid.html", nomination=nomination, bid=user_bid, min_contracts=min_contracts)


@bp.route("/<int:nomination_id>/match/", methods=["GET", "POST"])
@login_required
def match(nomination_id):
    nomination = db.session.get(Nomination, nomination_id)
    if g.user.id != nomination.player.matcher_id:
        abort(403)

    if request.method == "POST":
        is_match = request.form["match"] == "yes"
        if is_match:
            user_bid = get_user_bid_for_nomination(g.user.id, nomination.id)

            # Apply hometown discount if applicable
            if nomination.player.hometown_discount:
                discounted_value = int(nomination.bids[0].value * 0.9)
                # Enforce minimum bid value
                user_bid.value = max(discounted_value, get_minimum_bid_value())
            else:
                user_bid.value = nomination.bids[0].value

            nomination.player.manager_id = g.user.id
            db.session.add(user_bid)
            db.session.add(nomination)

            # Log audit event (sensitive)
            log_match_decision(nomination, accepted=True, user=g.user)

            db.session.commit()
            current_app.logger.info(
                f"Match for nomination {nomination} accepted by {g.user}."
            )
        else:
            close_nomination(nomination)

            # Log audit event (sensitive)
            log_match_decision(nomination, accepted=False, user=g.user)
            db.session.commit()

            current_app.logger.info(
                f"Match for nomination {nomination} declined by {g.user}."
            )

        # assign_nominated_player_to_team(nomination)
        add_auction_won_notification(nomination)

        return redirect(url_for("auction.index"))

    # Calculate discounted bid value for display
    winning_bid = nomination.bids[0].value if nomination.bids else 0
    discounted_bid = None
    if nomination.player.hometown_discount and winning_bid:
        discounted_value = int(winning_bid * 0.9)
        discounted_bid = max(discounted_value, get_minimum_bid_value())

    return render_template(
        "auction/match.html",
        nomination=nomination,
        winning_bid=winning_bid,
        discounted_bid=discounted_bid
    )


@bp.route("/<int:nomination_id>/edit/", methods=["GET", "POST"])
@login_required
@admin_required
def edit(nomination_id):
    nomination = db.session.get(Nomination, nomination_id)
    if nomination is None:
        abort(404, f"Nomination for id {nomination_id} doesn't exist.")

    if request.method == "POST":
        slot_id = request.form["slot_id"]
        winner_id = request.form["winner_id"] or None
        action = request.form["action"]

        if action.lower() == "delete":
            if nomination.player.matcher_id:
                remove_auction_match_notification(nomination)
            if nomination.player.manager_id:
                unassign_nominated_player_to_team(nomination)
            nomination_str = str(nomination)
            db.session.delete(nomination)
            db.session.commit()
            current_app.logger.info(f"Nomination {nomination_str} deleted by {g.user}.")
            return redirect(url_for("auction.index"))
        else:
            error = None
            if not slot_id:
                error = "Auction closes at date & time is required."

            if error:
                current_app.logger.error(
                    f"User {g.user} could not update nomination {nomination} because of error: {error}"
                )
                flash(error)
            else:
                # Track changes for audit log
                changes = {}
                old_slot_id = nomination.slot_id
                old_winner_id = nomination.player.manager_id

                if old_slot_id != int(slot_id):
                    old_slot = db.session.get(Slot, old_slot_id)
                    new_slot = db.session.get(Slot, int(slot_id))
                    changes['slot'] = {
                        'old': f"Round {old_slot.round} - {old_slot.closes_at}" if old_slot else None,
                        'new': f"Round {new_slot.round} - {new_slot.closes_at}" if new_slot else None
                    }

                if old_winner_id != (int(winner_id) if winner_id else None):
                    old_winner = db.session.get(User, old_winner_id) if old_winner_id else None
                    new_winner = db.session.get(User, int(winner_id)) if winner_id else None
                    changes['winner'] = {
                        'old': old_winner.team_name if old_winner else None,
                        'new': new_winner.team_name if new_winner else None
                    }

                if nomination.player.matcher_id:
                    remove_auction_match_notification(nomination)
                if (
                    nomination.player.matcher_id
                    and nomination.player.manager_id != winner_id
                ):
                    unassign_nominated_player_to_team(nomination)
                nomination.slot_id = slot_id
                nomination.player.manager_id = winner_id
                db.session.add(nomination)

                # Log audit event if there were changes
                if changes:
                    log_nomination_edit(nomination, changes, user=g.user)

                db.session.commit()
                current_app.logger.info(f"Nomination {nomination} updated by {g.user}.")
                if nomination.player.matcher_id:
                    # TODO: Only add if notification hasn't been sent yet
                    add_auction_match_notification(nomination, get_match_time_hours())
                return redirect(url_for("auction.index"))

    users = db.session.execute(db.select(User).order_by(User.team_name)).scalars().all()
    slots = get_open_slots()
    current_slot = db.session.get(Slot, nomination.slot_id)
    slots.append(current_slot)
    convert_slots_timezone(slots, "UTC", "US/Eastern")
    rounds = group_slots_by_round(slots)

    return render_template(
        "auction/edit.html",
        nomination=nomination,
        positions=POSITIONS,
        teams=TEAMS,
        users=users,
        rounds=rounds,
    )


@bp.route("/<int:player_id>/sign/", methods=["GET", "POST"])
@login_required
def sign(player_id):
    player = db.session.get(Player, player_id)
    if player is None:
        abort(404, f"Player for id {player_id} doesn't exist.")

    # Not sure why player.nomination returns a list, but it should always be len 1 so
    # this should be fine.
    user_bid = get_user_bid_for_nomination(g.user.id, player.nomination[0].id)
    minimum_total_salary = get_contract_options_by_year(get_minimum_total_salary())
    last_year = list(minimum_total_salary)[0] - 1
    options = dict()
    for year, salary in minimum_total_salary.items():
        if user_bid.value >= salary:
            options[year] = math.ceil(user_bid.value / (year - last_year))

    if request.method == "POST":
        contract = request.form["contract"] or None
        action = request.form["action"]

        if action.lower() == "reset":
            contract = None

        error = None

        try:
            contract = int(contract)
        except ValueError:
            error = "Contract must be an integer."

        if contract not in options:
            error = "Invalid contract option."

        if error is not None:
            current_app.logger.error(
                f"User {g.user} could not sign player because of error: {error}"
            )
            flash(error)
        else:
            player.contract = contract
            player.salary = options[contract]
            db.session.add(player)

            # Log audit event
            log_player_signed(player, contract, options[contract], user=g.user)

            db.session.commit()
            current_app.logger.info(
                f"Player contract set to {contract} with salary {options[contract]} by "
                f"{g.user}."
            )
            return redirect(url_for("rosters.index"))

    # Calculate reference table for minimum contracts
    min_contracts = {}
    for year, min_salary in minimum_total_salary.items():
        min_contracts[year] = {
            'total': min_salary,
            'annual': math.ceil(min_salary / (year - last_year))
        }

    return render_template(
        "auction/sign.html",
        player=player,
        options=options,
        min_contracts=min_contracts,
        user_bid=user_bid.value
    )


@bp.route("/admin/sign/<int:player_id>/", methods=["GET", "POST"])
@login_required
@admin_required
def admin_sign(player_id):
    """Admin route to sign a player on behalf of any manager."""
    player = db.session.get(Player, player_id)
    if player is None:
        abort(404, f"Player for id {player_id} doesn't exist.")

    # Get all users for manager selection
    users = db.session.execute(db.select(User).order_by(User.team_name)).scalars().all()

    if request.method == "POST":
        manager_id = request.form.get("manager_id")
        contract = request.form.get("contract")

        error = None

        if not manager_id:
            error = "Manager is required."
        elif not contract:
            error = "Contract is required."

        if not error:
            try:
                manager_id = int(manager_id)
                contract = int(contract)
            except ValueError:
                error = "Invalid manager or contract value."

        if not error:
            # Get the manager's bid for this nomination
            if not player.nomination:
                error = "Player has no associated nomination."
            else:
                user_bid = get_user_bid_for_nomination(manager_id, player.nomination[0].id)
                if not user_bid:
                    error = "Selected manager has no bid for this player."

        if not error:
            # Calculate contract options based on bid value
            minimum_total_salary = get_contract_options_by_year(get_minimum_total_salary())
            last_year = list(minimum_total_salary)[0] - 1
            options = dict()
            for year, salary in minimum_total_salary.items():
                if user_bid.value >= salary:
                    options[year] = math.ceil(user_bid.value / (year - last_year))

            if contract not in options:
                error = "Invalid contract option for this bid value."

        if error:
            flash(error, "error")
        else:
            # Assign player to selected manager
            manager = db.session.get(User, manager_id)
            player.manager_id = manager_id
            player.contract = contract
            player.salary = options[contract]
            db.session.add(player)

            # Log audit event
            log_admin_player_sign(player, manager, contract, options[contract], user=g.user)

            db.session.commit()

            current_app.logger.info(
                f"Admin {g.user} signed player {player.name} to {manager.team_name} "
                f"with contract {contract} and salary {options[contract]}."
            )
            flash(f"Player {player.name} signed to {manager.team_name}.", "success")
            return redirect(url_for("admin.players.index"))

    # Calculate contract options for display (if player has nomination)
    contract_options_by_user = {}
    minimum_total_salary = get_contract_options_by_year(get_minimum_total_salary())
    last_year = list(minimum_total_salary)[0] - 1

    if player.nomination:
        for user in users:
            user_bid = get_user_bid_for_nomination(user.id, player.nomination[0].id)
            if user_bid:
                options = dict()
                for year, salary in minimum_total_salary.items():
                    if user_bid.value >= salary:
                        options[year] = math.ceil(user_bid.value / (year - last_year))
                contract_options_by_user[user.id] = {
                    "bid": user_bid.value,
                    "options": options
                }

    # Calculate reference table for minimum contracts
    min_contracts = {}
    for year, min_salary in minimum_total_salary.items():
        min_contracts[year] = {
            'total': min_salary,
            'annual': math.ceil(min_salary / (year - last_year))
        }

    return render_template(
        "auction/admin_sign.html",
        player=player,
        users=users,
        contract_options=contract_options_by_user,
        min_contracts=min_contracts
    )


@bp.route("/results/")
@login_required
def results():
    def generate(headers, rows):
        yield ",".join(headers) + "\n"
        for row in rows:
            yield ",".join(row) + "\n"

    nominations = db.session.execute(
        db.select(Nomination)
        .join(Player, Nomination.player_id == Player.id)
        .join(Slot, Nomination.slot_id == Slot.id)
        .where(Player.manager_id.is_not(None))
        .order_by(Slot.closes_at.asc())
    )
    results_headers = [
        "Fantrax ID",
        "Round",
        "Player",
        "Team",
        "Position",
        "Winner",
        "Salary",
        "Contract",
        "Bids",
    ]
    results_rows = [
        [
            nomination.player.fantrax_id,
            str(nomination.slot.round),
            nomination.player.name,
            nomination.player.team,
            nomination.player.position.replace(",", ";"),
            nomination.player.manager_user.team_name,
            str(nomination.player.salary),
            str(nomination.player.contract),
            ";".join([str(b.value) for b in nomination.bids]),
        ]
        for nomination in nominations.scalars()
    ]
    current_app.logger.info(f"Results downloaded by {g.user}.")

    return Response(
        generate(results_headers, results_rows),
        mimetype="text/csv",
        headers={
            "Content-Disposition": 'attachment; filename="the-doo-auction-results.csv"'
        },
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

    nomination.player.manager_id = winning_user.id
    db.session.add(nomination)
    db.session.commit()


def assign_nominated_player_to_team(nomination):
    nomination.player.status = nomination.winner_user.team
    db.session.add(nomination)
    db.session.commit()


def unassign_nominated_player_to_team(nomination):
    nomination.player.manager_id = None
    nomination.player.contract = None
    nomination.player.salary = None
    db.session.add(nomination)
    db.session.commit()


def convert_slots_timezone(slots, from_tz, to_tz):
    for slot in slots:
        slot.closes_at = (
            pytz.timezone(from_tz)
            .localize(slot.closes_at)
            .astimezone(pytz.timezone(to_tz))
        )
        slot.nomination_opens_at = (
            pytz.timezone(from_tz)
            .localize(slot.nomination_opens_at)
            .astimezone(pytz.timezone(to_tz))
        )
        slot.nomination_closes_at = (
            pytz.timezone(from_tz)
            .localize(slot.nomination_closes_at)
            .astimezone(pytz.timezone(to_tz))
        )

    return slots


@bp.route("/boss")
def boss():
    """Boss button - shows a fake spreadsheet for when the boss walks by."""
    return render_template("boss.html", now=datetime.now())
