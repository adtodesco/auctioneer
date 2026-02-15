"""Configuration management blueprint."""

import json
from flask import Blueprint, flash, g, redirect, render_template, request, url_for
from . import db
from .audit_log import log_config_change
from .auth import admin_required, login_required
from .model import Config


bp = Blueprint("config", __name__, url_prefix="/config")


@bp.route("/")
@login_required
@admin_required
def index():
    """List all configuration values."""
    configs = Config.query.order_by(Config.key).all()
    return render_template("config/index.html", configs=configs)


@bp.route("/<key>/edit/", methods=["GET", "POST"])
@login_required
@admin_required
def edit(key):
    """Edit a configuration value."""
    config = Config.query.filter_by(key=key).first_or_404()

    if request.method == "POST":
        value = request.form["value"]
        error = None

        # Validate based on type
        if config.value_type == "int":
            try:
                int(value)
            except ValueError:
                error = "Value must be an integer."
        elif config.value_type == "float":
            try:
                float(value)
            except ValueError:
                error = "Value must be a number."
        elif config.value_type == "json":
            try:
                json.loads(value)
            except json.JSONDecodeError:
                error = "Value must be valid JSON."

        if error:
            flash(error, "error")
        else:
            old_value = config.value
            config.value = value

            # Log audit event
            log_config_change(key, old_value, value, user=g.user)

            db.session.commit()
            flash(f"Configuration '{key}' updated successfully.", "success")
            return redirect(url_for("admin.config.index"))

    return render_template("config/edit.html", config=config)


# Configuration utility functions

def get_config(key, default=None):
    """Get a configuration value from the database.

    Args:
        key: The configuration key to retrieve
        default: Default value if key not found or empty

    Returns:
        The configuration value, parsed according to its value_type
    """
    config = Config.query.filter_by(key=key).first()

    if not config:
        if default is not None:
            return default
        raise ValueError(f"Configuration key '{key}' not found")

    # Return default if value is empty
    if not config.value or config.value.strip() == "":
        if default is not None:
            return default
        raise ValueError(f"Configuration '{key}' is not set. Please ask the league manager to configure it.")

    # Parse value based on type
    if config.value_type == "int":
        return int(config.value)
    elif config.value_type == "float":
        return float(config.value)
    elif config.value_type == "json":
        return json.loads(config.value)
    else:
        return config.value


def get_salary_cap():
    """Get the salary cap dictionary (calendar year -> cap value).

    Returns dict with integer keys (e.g., 2026, 2027, etc.).
    """
    data = get_config("SALARY_CAP", {})
    # Convert string keys from JSON to integers
    return {int(year): cap for year, cap in data.items()}


def get_minimum_total_salary():
    """Get the minimum total salary dictionary (contract year -> min value).

    Returns dict with integer keys (1-10 representing contract years).
    """
    data = get_config("MINIMUM_TOTAL_SALARY", {})
    # Convert string keys from JSON to integers
    return {int(year): salary for year, salary in data.items()}


def get_minimum_bid_value():
    """Get the minimum bid value."""
    return get_config("MINIMUM_BID_VALUE", 11)


def get_match_time_hours():
    """Get the number of hours a matcher has to respond."""
    return get_config("MATCH_TIME_HOURS", 24)


def get_max_nominations_normal():
    """Get the maximum number of nominations in normal mode."""
    return get_config("MAX_NOMINATIONS_NORMAL", 2)


def get_max_nominations_urgent():
    """Get the maximum number of nominations in urgent mode."""
    return get_config("MAX_NOMINATIONS_URGENT", 3)


def get_urgent_threshold_hours():
    """Get the threshold in hours before slot close to enter urgent mode."""
    return get_config("URGENT_THRESHOLD_HOURS", 24)


def get_notification_alert_hours():
    """Get the number of hours before an event to send alert notifications."""
    return get_config("NOTIFICATION_ALERT_HOURS", 2)


def get_webhook_url():
    """Get the Slack webhook URL for notifications."""
    return get_config("WEBHOOK_URL", "")
