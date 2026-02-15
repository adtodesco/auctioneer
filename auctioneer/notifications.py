"""Notification routing layer - automatically uses Discord or Slack based on config."""

from .config import get_config


def get_notification_module():
    """Get the appropriate notification module based on configuration."""
    notification_type = get_config("NOTIFICATION_TYPE", "discord").lower()

    if notification_type == "discord":
        from . import discord as notification_module
    elif notification_type == "slack":
        from . import slack as notification_module
    else:
        raise ValueError(f"Invalid NOTIFICATION_TYPE: {notification_type}. Must be 'discord' or 'slack'")

    return notification_module


# Export all notification functions dynamically
def add_nomination_period_begun_notification(*args, **kwargs):
    return get_notification_module().add_nomination_period_begun_notification(*args, **kwargs)


def add_nomination_period_end_notification(*args, **kwargs):
    return get_notification_module().add_nomination_period_end_notification(*args, **kwargs)


def add_auctions_close_notification(*args, **kwargs):
    return get_notification_module().add_auctions_close_notification(*args, **kwargs)


def add_player_nominated_notification(*args, **kwargs):
    return get_notification_module().add_player_nominated_notification(*args, **kwargs)


def add_auction_won_notification(*args, **kwargs):
    return get_notification_module().add_auction_won_notification(*args, **kwargs)


def add_auction_match_notification(*args, **kwargs):
    return get_notification_module().add_auction_match_notification(*args, **kwargs)


def remove_nomination_period_begun_notification(*args, **kwargs):
    return get_notification_module().remove_nomination_period_begun_notification(*args, **kwargs)


def remove_nomination_period_end_notification(*args, **kwargs):
    return get_notification_module().remove_nomination_period_end_notification(*args, **kwargs)


def remove_auctions_close_notification(*args, **kwargs):
    return get_notification_module().remove_auctions_close_notification(*args, **kwargs)


def remove_auction_match_notification(*args, **kwargs):
    return get_notification_module().remove_auction_match_notification(*args, **kwargs)
