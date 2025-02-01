import csv
from datetime import datetime, timedelta

from . import db
from .model import Bid, Nomination, Player, Slot, User


def day_range_to_times(day_range):
    dt_format = "%Y-%m-%d %H:%M:%S"
    start = datetime.utcnow() + timedelta(days=day_range[1])
    end = datetime.utcnow() + timedelta(days=day_range[0])
    return start.strftime(dt_format), end.strftime(dt_format)


def get_user_bid_for_nomination(user_id, nomination_id):
    bid = db.session.execute(
        db.select(Bid)
        .where(Bid.user_id == user_id)
        .where(Bid.nomination_id == nomination_id)
    ).scalar()

    return bid


def get_open_slots(day_range=None):
    statement = db.select(Slot).where(~db.exists().where(Nomination.slot_id == Slot.id))
    if day_range:
        statement = statement.where(
            Slot.closes_at.between(*day_range_to_times(day_range))
        ).order_by(Slot.closes_at)
    slots = db.session.execute(statement)

    return slots


def get_open_slots_for_user(user_id, day_range=None, max_nominations_per_round=None):
    slots = get_open_slots(day_range)

    if max_nominations_per_round:
        statement = (
            db.select(Slot.round, db.func.count("*"))
            .select_from(Nomination)
            .join(Slot)
            .where(Nomination.nominator_id == user_id)
        )
        statement = statement.group_by(Slot.round)

        user_nominations = db.session.execute(statement)
        user_nominations_per_round = {n.round: int(n.count) for n in user_nominations}

        filtered_slots = list()
        for slot in slots.scalars():
            if (
                user_nominations_per_round.get(slot.round, 0)
                < max_nominations_per_round
            ):
                filtered_slots.append(slot)

        slots = filtered_slots

    return slots


def group_slots_by_round(slots):
    rounds = dict()
    for slot in slots:
        if slot.round not in rounds:
            rounds[slot.round] = list()
        rounds[slot.round].append(slot)

    for round in rounds.keys():
        rounds[round] = sorted(rounds[round], key=lambda b: b.closes_at)

    return rounds


def players_from_fantrax_export(file, users):
    with open(file) as f:
        reader = csv.DictReader(f)
        players = list()
        short_name_to_user = {user.short_team_name: user.id for user in users}
        for player in reader:
            if player["Status"] == "FA":
                salary = None
                contract = None
            else:
                salary = int(float(player["Salary"]))
                contract = int(player["Contract"])

            players.append(
                Player(
                    fantrax_id=player["ID"],
                    name=player["Player"],
                    team=player["Team"],
                    position=player["Position"],
                    salary=salary,
                    contract=contract,
                    manager_id=short_name_to_user.get(player["Status"]),
                )
            )

    return players


def users_from_file(file):
    with open(file) as f:
        reader = csv.DictReader(f)
        users = list()
        for team in reader:
            users.append(
                User(
                    team_name=team["team_name"],
                    short_team_name=team["short_team_name"],
                    tiebreaker_order=int(team["tiebreaker_order"]),
                    slack_id=team["slack_id"],
                    is_league_manager=team["is_league_manager"] == "TRUE",
                )
            )

    return users
