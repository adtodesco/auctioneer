from datetime import datetime, timedelta

import pytz
from slack_sdk import WebhookClient

from auctioneer import db
from auctioneer.model import Notification


def add_nomination_period_begun_notification(
    block_number, block_opens_at, block_closes_at, max_nominations_per_block
):
    block_closes_at = block_closes_at.replace(tzinfo=pytz.utc)
    block_closes_at_et = block_closes_at.astimezone(pytz.timezone("US/Eastern"))

    notification = Notification(
        title=(
            f":incoming_envelope:  *Block {block_number} nomination period has begun!* "
        ),
        message=(
            f"The block {block_number} nomination period has begun and will last until " 
            f"{block_closes_at_et.strftime('%Y-%m-%d @ %-I:%M %p')} ET. Head to "
            f"http://thedooauction.com to make up to {max_nominations_per_block} "
            f"nominations in this block!"
        ),
        send_at=block_opens_at,
    )

    db.session.add(notification)
    db.session.commit()

    return notification


def add_nomination_period_end_notification(
    block_number, block_closes_at, max_nominations_per_block, alert_hours=2
):
    block_closes_at = block_closes_at.replace(tzinfo=pytz.utc)
    block_closes_at_et = block_closes_at.astimezone(pytz.timezone("US/Eastern"))

    notification = Notification(
        title=(
            f":envelope:  *Block {block_number} nomination period ends in {alert_hours}"
            f" hours!*"
        ),
        message=(
            f"The block {block_number} nomination period will start ending in "
            f"{alert_hours} hours. If you have not made your block {block_number} "
            f"nominations head to http://thedooauction.com to make up to "
            f"{max_nominations_per_block} nominations by "
            f"{block_closes_at_et.strftime('%Y-%m-%d @ %-I:%M %p')} ET."
        ),
        send_at=block_closes_at - timedelta(hours=alert_hours),
    )

    db.session.add(notification)
    db.session.commit()

    return notification


def add_auctions_close_notification(
    block_number, auctions_start_closing_at, alert_hours=2
):
    notification = Notification(
        title=(
            f":rotating_light:  *Block {block_number} auctions closes in {alert_hours} "
            f"hours!*"
        ),
        message=(
            f"Block {block_number} auctions will start closing in {alert_hours} hours. "
            f"Get your bids in and make your final adjustments before the clock runs "
            f"out!"
        ),
        send_at=auctions_start_closing_at - timedelta(hours=alert_hours),
    )

    db.session.add(notification)
    db.session.commit()

    return notification


def add_player_nominated_notification(nomination):
    notification = Notification(
        title=":mega:  *A player has been nominated!*",
        message=(
            f"<@{nomination.nominator_user.slack_id}> has nominated "
            f"{nomination.player.name} ({nomination.player.position}, "
            f"{nomination.player.team }) in block {nomination.slot.block}."
        ),
        send_at=datetime.utcnow(),
    )

    db.session.add(notification)
    db.session.commit()

    return notification


def add_auction_won_notification(nomination):
    notification = Notification(
        title=":moneybag:  *An auction has been won!*",
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
        title=":stopwatch:  *An auction has closed and is pending a match!*",
        message=(
            f"<@{nomination.matcher_user.slack_id}> has {match_time_hours} hours to "
            f"accept or decline to match the highest bid for {nomination.player.name}."
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
        text=notification.title,
        blocks=format_slack_blocks(notification.title, notification.message)
    )
    if response.status_code == 200:
        notification.sent = True
        db.session.add(notification)
        db.session.commit()
        return True
    else:
        return False
