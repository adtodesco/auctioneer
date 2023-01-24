import os
from datetime import datetime, timedelta

import click
from flask import current_app

from . import db
from .auction import MAX_NOMINATIONS_PER_BLOCK, NOMINATION_DAY_RANGE
from .model import Nomination, Notification, Slot
from .slack import (
    add_auction_won_notification,
    add_auctions_close_notification,
    add_nomination_period_begun_notification,
    add_nomination_period_end_notification,
    send_notification,
)
from .utils import close_nomination, group_slots_by_block


def init_db():
    from .model import Bid, Nomination, Notification, Player, Slot, User

    with current_app.app_context():
        db.drop_all()
        db.create_all()

    with current_app.open_resource("data/players.csv") as f:
        player_lines = list(
            s.decode("utf-8").strip("\n").replace('"', "").split(",")
            for s in f.readlines()
        )

    players = [
        Player(fantrax_id=player[0], name=player[1], team=player[2], position=player[3])
        for player in player_lines
    ]
    db.session.add_all(players)

    with current_app.open_resource("data/slots.csv") as f:
        slot_lines = list(
            s.decode("utf-8").strip("\n").split(",") for s in f.readlines()
        )

    slots = [
        Slot(block=slot[0], ends_at=datetime.strptime(slot[1], "%Y-%m-%d %H:%M:%S"))
        for slot in slot_lines
    ]
    db.session.add_all(slots)

    blocks = group_slots_by_block(slots)
    for num, slots in blocks.items():
        block_opens_at = slots[-1].ends_at - timedelta(days=NOMINATION_DAY_RANGE[1])
        block_closes_at = slots[0].ends_at - timedelta(days=NOMINATION_DAY_RANGE[0])
        add_nomination_period_begun_notification(
            num, block_opens_at, block_closes_at, MAX_NOMINATIONS_PER_BLOCK
        )
        add_nomination_period_end_notification(num, block_closes_at, MAX_NOMINATIONS_PER_BLOCK)
        add_auctions_close_notification(num, slots[0].ends_at)

    db.session.commit()


@click.command("init-db")
def init_db_command():
    """Clear the existing data and create new tables."""
    init_db()
    click.echo(f"{datetime.utcnow().isoformat()}: Initialized the database.")


def close_nominations():
    current_datetime = datetime.utcnow()
    match_datetime = current_datetime - timedelta(days=1)
    statement = (
        db.select(Nomination)
        .join(Slot)
        .where(Nomination.winner_id.is_(None))
        .where(
            (Nomination.matcher_id.is_(None) & (current_datetime > Slot.ends_at))
            | (Nomination.matcher_id.is_not(None) & (match_datetime > Slot.ends_at))
        )
    )
    nominations = db.session.execute(statement).scalars().all()
    for nomination in nominations:
        close_nomination(nomination)
        add_auction_won_notification(nomination)

    return nominations


@click.command("close-nominations")
def close_nominations_command():
    """Close any open nominations passed the slot end and/or match end."""
    nominations = close_nominations()
    click.echo(
        f"{datetime.utcnow().isoformat()}: Closed {len(nominations)} nominations."
    )


def send_notifications(webhook_url):
    statement = (
        db.select(Notification)
        .where(Notification.sent.is_(False))
        .where(Notification.send_at < datetime.utcnow())
    )
    notifications = db.session.execute(statement).scalars().all()

    notifications_sent = list()
    for notification in notifications:
        success = send_notification(notification, webhook_url)
        if success:
            notifications_sent.append(notification)

    return notifications_sent


@click.command("send-notifications")
def send_notifications_command():
    """Send unsent notifications passed their send_at timestamp."""
    webhook_url = os.environ.get("WEBHOOK_URL")
    if not webhook_url:
        raise RuntimeError("WEBHOOK_URL env variable is not set!")
    notifications = send_notifications(webhook_url)
    click.echo(
        f"{datetime.utcnow().isoformat()}: Sent {len(notifications)} notifications."
    )
