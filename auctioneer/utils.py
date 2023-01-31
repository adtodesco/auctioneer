from datetime import datetime, timedelta

import pytz

from . import db
from .model import Bid, Nomination, Slot, User


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
            Slot.ends_at.between(*day_range_to_times(day_range))
        )
    slots = db.session.execute(statement)

    return slots


def get_open_slots_for_user(user_id, day_range=None, max_nominations_per_block=None):
    slots = get_open_slots(day_range)

    if max_nominations_per_block:
        statement = (
            db.select(Slot.block, db.func.count("*"))
            .select_from(Nomination)
            .join(Slot)
            .where(Nomination.nominator_id == user_id)
        )
        if day_range:
            statement = statement.where(
                Slot.ends_at.between(*day_range_to_times(day_range))
            )
        statement = statement.group_by(Slot.block)

        user_nominations = db.session.execute(statement)
        user_nominations_per_block = {n.block: int(n.count) for n in user_nominations}

        filtered_slots = list()
        for slot in slots.scalars():
            if (
                user_nominations_per_block.get(slot.block, 0)
                < max_nominations_per_block
            ):
                filtered_slots.append(slot)

        slots = filtered_slots

    return slots


def group_slots_by_block(slots):
    blocks = dict()
    for slot in slots:
        if slot.block not in blocks:
            blocks[slot.block] = list()
        blocks[slot.block].append(slot)

    for block in blocks.keys():
        blocks[block] = sorted(blocks[block], key=lambda b: b.ends_at)

    return blocks


def drop_to_tiebreaker_bottom(winning_user):
    users = db.session.execute(db.select(User)).scalars().all()

    updates = dict()
    max_tiebreaker_order = 0
    for user in users:
        if (
            user.tiebreaker_order is not None
            and user.tiebreaker_order > winning_user.tiebreaker_order
        ):
            if user.tiebreaker_order > max_tiebreaker_order:
                max_tiebreaker_order = user.tiebreaker_order
            updates[user.id] = user.tiebreaker_order - 1
            user.tiebreaker_order = None

    if updates:
        updates[winning_user.id] = max_tiebreaker_order
        winning_user.tiebreaker_order = None

        db.session.add_all(users)
        db.session.flush()
        for user_id, tiebreaker_order in updates.items():
            user = db.session.get(User, user_id)
            user.tiebreaker_order = tiebreaker_order
            db.session.add(user)
        db.session.commit()


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
        slot.ends_at = slot.ends_at.replace(tzinfo=pytz.utc).astimezone(
            pytz.timezone(timezone)
        )

    return slots
