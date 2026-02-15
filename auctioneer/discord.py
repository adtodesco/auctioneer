"""Discord notification utilities."""

from datetime import datetime, timedelta

import pytz
import requests
from flask import current_app

from . import db
from .config import get_config, get_notification_alert_minutes
from .model import Notification


def add_nomination_period_begun_notification(
    round_number, nominations_open_at, nominations_close_at
):
    nominations_close_at = nominations_close_at.replace(tzinfo=pytz.utc)
    nominations_close_at_et = nominations_close_at.astimezone(
        pytz.timezone("US/Eastern")
    )

    notification = Notification(
        title=(
            f":incoming_envelope:  **Round {round_number} nomination period has begun!** "
        ),
        message=(
            f"Round {round_number} nomination period has begun and will last until "
            f"{nominations_close_at_et.strftime('%Y-%m-%d @ %-I:%M %p')} ET. Head to "
            f"thedooauction.com to make nominations in this round!"
        ),
        send_at=nominations_open_at,
    )

    db.session.add(notification)
    db.session.commit()

    return notification


def remove_nomination_period_begun_notification(round_number):
    db.session.query(Notification).where(
        Notification.title.contains(f"Round {round_number} nomination period has begun")
    ).delete(synchronize_session=False)
    db.session.commit()


def add_nomination_period_end_notification(
    round_number, nominations_close_at, alert_minutes=None
):
    if alert_minutes is None:
        alert_minutes = get_notification_alert_minutes()

    nominations_close_at = nominations_close_at.replace(tzinfo=pytz.utc)
    nominations_close_at_et = nominations_close_at.astimezone(
        pytz.timezone("US/Eastern")
    )

    notification = Notification(
        title=(
            f":envelope:  **Round {round_number} nomination period ends in {alert_minutes}"
            f" minutes!**"
        ),
        message=(
            f"Round {round_number} nomination period ends in "
            f"{alert_minutes} minutes. If you have not made your round {round_number} "
            f"nominations head to thedooauction.com to make them by "
            f"{nominations_close_at_et.strftime('%Y-%m-%d @ %-I:%M %p')} ET."
        ),
        send_at=nominations_close_at - timedelta(minutes=alert_minutes),
    )

    db.session.add(notification)
    db.session.commit()

    return notification


def remove_nomination_period_end_notification(round_number):
    db.session.query(Notification).where(
        Notification.title.contains(f"Round {round_number} nomination period ends")
    ).delete(synchronize_session=False)
    db.session.commit()


def add_auctions_close_notification(
    round_number, auctions_start_closing_at, alert_minutes=None
):
    if alert_minutes is None:
        alert_minutes = get_notification_alert_minutes()

    notification = Notification(
        title=(
            f":rotating_light:  **Round {round_number} auctions close in {alert_minutes} "
            f"minutes!**"
        ),
        message=(
            f"Round {round_number} auctions will start closing in {alert_minutes} minutes. "
            f"Get your bids in and make your final adjustments before the clock runs "
            f"out!"
        ),
        send_at=auctions_start_closing_at - timedelta(minutes=alert_minutes),
    )

    db.session.add(notification)
    db.session.commit()

    return notification


def remove_auctions_close_notification(round_number):
    db.session.query(Notification).where(
        Notification.title.contains(f"Round {round_number} auctions close")
    ).delete(synchronize_session=False)
    db.session.commit()


def add_player_nominated_notification(nomination):
    user_mention = f"<@{nomination.nominator_user.discord_id}>" if nomination.nominator_user.discord_id else nomination.nominator_user.team_name
    notification = Notification(
        title=":mega:  **A player has been nominated!**",
        message=(
            f"{user_mention} has nominated "
            f"{str(nomination)}) in round {nomination.slot.round}."
        ),
        send_at=datetime.utcnow(),
    )

    db.session.add(notification)
    db.session.commit()

    return notification


def add_auction_won_notification(nomination):
    user_mention = f"<@{nomination.player.manager_user.discord_id}>" if nomination.player.manager_user.discord_id else nomination.player.manager_user.team_name
    notification = Notification(
        title=":moneybag:  **An auction has been won!**",
        message=(
            f"{user_mention} has won the auction for "
            f"{str(nomination)} with a bid of ${nomination.bids[0].value}!"
        ),
        send_at=datetime.utcnow(),
    )

    db.session.add(notification)
    db.session.commit()

    return notification


MATCH_NOTIFICATION_TITLE = (
    ":stopwatch:  **An auction has closed and is pending a match!**"
)


def add_auction_match_notification(nomination, match_time_hours):
    user_mention = f"<@{nomination.player.matcher_user.discord_id}>" if nomination.player.matcher_user.discord_id else nomination.player.matcher_user.team_name
    notification = Notification(
        title=MATCH_NOTIFICATION_TITLE,
        message=(
            f"{user_mention} has {match_time_hours} hours to "
            f"accept or decline to match the highest bid for {str(nomination)}."
        ),
        send_at=nomination.slot.closes_at,
    )

    db.session.add(notification)
    db.session.commit()

    return notification


def remove_auction_match_notification(nomination):
    notifications = db.session.execute(
        db.select(Notification)
        .where(Notification.title.is_(MATCH_NOTIFICATION_TITLE))
        .where(Notification.message.contains(str(nomination)))
        .where(Notification.sent.is_(False))
    )
    notification_count = 0
    for notification in notifications.scalars():
        notification_count += 1
        db.session.delete(notification)

    db.session.commit()
    if notification_count > 1:
        current_app.logger.warning(
            f"Multiple auction match notifications for nomination {nomination}: "
            f"{notifications}."
        )


def send_notification(notification, webhook_url):
    """Send a notification via Discord webhook.

    Discord webhook format is different from Slack - uses 'content' and 'embeds'.
    """
    # Build Discord embed
    payload = {
        "content": notification.title,
        "embeds": [{
            "description": notification.message,
            "color": 3447003  # Blue color
        }]
    }

    try:
        response = requests.post(webhook_url, json=payload)

        if response.status_code in [200, 204]:
            notification.sent = True
            db.session.add(notification)
            db.session.commit()
            return True
        else:
            current_app.logger.error(
                f"Failed to send Discord notification {notification} with status {response.status_code}: {response.text}"
            )
            return False
    except Exception as e:
        current_app.logger.error(
            f"Exception sending Discord notification {notification}: {str(e)}"
        )
        return False
