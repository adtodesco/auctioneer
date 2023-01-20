from datetime import datetime, timedelta

import pytz
from slack_sdk import WebhookClient

from auctioneer import db
from auctioneer.model import Notification


def add_block_open_notification(
    block_number, block_opens_at, block_closes_at, max_nominations_per_block
):
    block_closes_at = block_closes_at.replace(tzinfo=pytz.utc)
    block_closes_at_et = block_closes_at.astimezone(pytz.timezone("US/Eastern"))

    notification = Notification(
        title=f":unlock: *Block {block_number} is now open for nominations!*",
        message=(
            f"Make up to {max_nominations_per_block} nominations in block "
            f"{block_number} by {block_closes_at_et.strftime('%Y-%m-%d @ %-I:%M %p')} "
            f"ET."
        ),
        send_at=block_opens_at,
    )

    db.session.add(notification)
    db.session.commit()

    return notification


def add_block_closing_notification(
    block_number, block_closes_at, max_nominations_per_block, alert_hours=5
):
    block_closes_at = block_closes_at.replace(tzinfo=pytz.utc)
    block_closes_at_et = block_closes_at.astimezone(pytz.timezone("US/Eastern"))

    notification = Notification(
        title=(
            f":lock: *Block {block_number} will close for nominations in {alert_hours} "
            "hours!*"
        ),
        message=(
            f"Make up to {max_nominations_per_block} nominations in block "
            f"{block_number} by {block_closes_at_et.strftime('%Y-%m-%d @ %-I:%M %p')} "
            f"ET."
        ),
        send_at=block_closes_at - timedelta(hours=alert_hours),
    )

    db.session.add(notification)
    db.session.commit()

    return notification


def add_auctions_closing_notification(
    block_number, auctions_start_closing_at, alert_hours=5
):
    notification = Notification(
        title=(
            f":incoming_envelope: *Block {block_number} auctions will start closing in "
            f"{alert_hours} hours!*"
        ),
        message="Get your bids in and/or make final adjustments before its too late!",
        send_at=auctions_start_closing_at - timedelta(hours=alert_hours),
    )

    db.session.add(notification)
    db.session.commit()

    return notification


def add_auction_won_notification(nomination):
    notification = Notification(
        title=":moneybag: *An auction has been won!*",
        message=(
            f"<@{nomination.winner_user.slack_id}> has won the auction for "
            f"{nomination.player.name} with a bid of ${nomination.bids[0].value}!"
        ),
        send_at=datetime.utcnow(),
    )

    db.session.add(notification)
    db.session.commit()

    return notification


def add_auction_match_notification(nomination, match_time_hours):
    notification = Notification(
        title=":stopwatch: *An auction has closed and is pending a match!*",
        message=(
            f"<@{nomination.matcher_user.slack_id}> has {match_time_hours} hours to "
            f"match the highest bid for {nomination.player.name}."
        ),
        send_at=datetime.utcnow(),
    )

    db.session.add(notification)
    db.session.commit()

    return notification


def format_slack_blocks(title, message):
    return [
        {"type": "section", "text": {"type": "mrkdwn", "text": title}},
        {"type": "divider"},
        {"type": "section", "text": {"type": "mrkdwn", "text": message}},
    ]


def send_notification(notification, webhook_url):
    webhook = WebhookClient(webhook_url)
    response = webhook.send(
        blocks=format_slack_blocks(notification.title, notification.message)
    )
    if response.status_code == 200:
        notification.sent = True
        db.session.add(notification)
        db.session.commit()
        return True
    else:
        return False
