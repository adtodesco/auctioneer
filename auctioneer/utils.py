import csv
from datetime import datetime, timedelta

from . import db
from .model import Bid, Nomination, Player, Slot


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
        )
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


def players_from_fantrax_export(file):
    with open(file) as f:
        reader = csv.DictReader(f)
        players = list()
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
                    status=player["Status"],
                    salary=salary,
                    contract=contract,
                )
            )

    return players
