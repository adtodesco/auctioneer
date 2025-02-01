import os
from datetime import datetime, timedelta

import click
from flask import current_app

from . import db
from .auction import assign_nominated_player_to_team, close_nomination
from .model import Nomination, Notification, Slot
from .slack import add_auction_won_notification, send_notification
from .utils import players_from_fantrax_export, users_from_file


def init_db():
    # All models need to be imported before setting up the database
    from .model import (  # noqa: F401
        Bid,
        Nomination,
        Notification,
        Player,
        Slot,
        User,
    )

    with current_app.app_context():
        db.drop_all()
        db.create_all()

    users_file = os.path.join(current_app.root_path, "data", "users.csv")
    users = users_from_file(users_file)
    db.session.add_all(users)
    db.session.flush()

    players_file = os.path.join(current_app.root_path, "data", "players.csv")
    players = players_from_fantrax_export(players_file, users)
    db.session.add_all(players)

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
        .where(Nomination.player.manager_id.is_(None))
        .where(
            (
                Nomination.player.matcher_id.is_(None)
                & (current_datetime > Slot.closes_at)
            )
            | (
                Nomination.player.matcher_id.is_not(None)
                & (match_datetime > Slot.closes_at)
            )
        )
    )
    nominations = db.session.execute(statement).scalars().all()
    for nomination in nominations:
        close_nomination(nomination)
        # assign_nominated_player_to_team(nomination)
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
