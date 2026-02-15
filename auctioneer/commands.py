import json
import os
from datetime import datetime, timedelta

import click
from flask import current_app

from . import db
from .auction import close_nomination
from .config import get_config
from .model import Config, Nomination, Notification, Player, Slot
from .slack import add_auction_won_notification
from .slack import send_notification as send_slack_notification
from .discord import send_notification as send_discord_notification
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

    # Populate config values with defaults from 2026 season
    configs = [
        Config(
            key="SALARY_CAP",
            value=json.dumps({
                2026: 1282,
                2027: 1334,
                2028: 1387,
                2029: 1442,
                2030: 1500,
                2031: 1560,
                2032: 1623,
                2033: 1687,
                2034: 1755,
                2035: 1825,
            }),
            description="Salary cap per year (calendar years)",
            value_type="json",
        ),
        Config(
            key="MINIMUM_TOTAL_SALARY",
            value=json.dumps({
                1: 12,
                2: 30,
                3: 60,
                4: 104,
                5: 165,
                6: 258,
                7: 392,
                8: 584,
                9: 855,
                10: 1240,
            }),
            description="Minimum total salary required for contract years (year 1-10)",
            value_type="json",
        ),
        Config(
            key="MINIMUM_BID_VALUE",
            value="11",
            description="Minimum bid value allowed",
            value_type="int",
        ),
        Config(
            key="MATCH_TIME_HOURS",
            value="24",
            description="Number of hours a matcher has to respond",
            value_type="int",
        ),
        Config(
            key="MAX_NOMINATIONS_NORMAL",
            value="2",
            description="Maximum number of nominations in normal mode",
            value_type="int",
        ),
        Config(
            key="MAX_NOMINATIONS_URGENT",
            value="3",
            description="Maximum number of nominations in urgent mode",
            value_type="int",
        ),
        Config(
            key="URGENT_THRESHOLD_HOURS",
            value="24",
            description="Hours before slot close to enter urgent nomination mode",
            value_type="int",
        ),
        Config(
            key="NOTIFICATION_ALERT_HOURS",
            value="2",
            description="Hours before an event to send alert notifications",
            value_type="int",
        ),
        Config(
            key="SLACK_WEBHOOK_URL",
            value=os.environ.get("SLACK_WEBHOOK_URL", os.environ.get("WEBHOOK_URL", "")),
            description="Slack webhook URL for notifications",
            value_type="string",
        ),
        Config(
            key="DISCORD_WEBHOOK_URL",
            value=os.environ.get("DISCORD_WEBHOOK_URL", ""),
            description="Discord webhook URL for notifications",
            value_type="string",
        ),
        Config(
            key="NOTIFICATION_TYPE",
            value=os.environ.get("NOTIFICATION_TYPE", "discord"),
            description="Notification platform: 'slack' or 'discord'",
            value_type="string",
        ),
    ]
    db.session.add_all(configs)

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
        .join(Player, Nomination.player_id == Player.id)
        .where(Player.manager_id.is_(None))
        .where(
            (Player.matcher_id.is_(None) & (current_datetime > Slot.closes_at))
            | (Player.matcher_id.is_not(None) & (match_datetime > Slot.closes_at))
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


def send_notifications(webhook_url, send_func):
    statement = (
        db.select(Notification)
        .where(Notification.sent.is_(False))
        .where(Notification.send_at < datetime.utcnow())
    )
    notifications = db.session.execute(statement).scalars().all()

    notifications_sent = list()
    for notification in notifications:
        success = send_func(notification, webhook_url)
        if success:
            notifications_sent.append(notification)

    return notifications_sent


@click.command("send-notifications")
def send_notifications_command():
    """Send unsent notifications passed their send_at timestamp."""
    # Determine which platform to use
    notification_type = get_config("NOTIFICATION_TYPE", "discord").lower()

    if notification_type == "discord":
        webhook_url = get_config("DISCORD_WEBHOOK_URL", os.environ.get("DISCORD_WEBHOOK_URL", ""))
        send_func = send_discord_notification
    elif notification_type == "slack":
        webhook_url = get_config("SLACK_WEBHOOK_URL", os.environ.get("SLACK_WEBHOOK_URL", ""))
        send_func = send_slack_notification
    else:
        raise RuntimeError(f"Invalid NOTIFICATION_TYPE: {notification_type}. Must be 'slack' or 'discord'")

    if not webhook_url:
        raise RuntimeError(f"{notification_type.upper()} webhook URL is not set in config or environment!")

    notifications = send_notifications(webhook_url, send_func)
    click.echo(
        f"{datetime.utcnow().isoformat()}: Sent {len(notifications)} notifications via {notification_type}."
    )


