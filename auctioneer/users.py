"""User/Team management blueprint."""

from flask import Blueprint, flash, g, redirect, render_template, request, url_for

from . import db
from .audit_log import log_audit
from .auth import admin_required, login_required
from .model import User

bp = Blueprint("users", __name__, url_prefix="/users")


@bp.route("/")
@login_required
@admin_required
def index():
    """List all users/teams."""
    users = db.session.execute(
        db.select(User).order_by(User.team_name)
    ).scalars().all()
    return render_template("users/index.html", users=users)


@bp.route("/<int:user_id>/edit/", methods=["GET", "POST"])
@login_required
@admin_required
def edit(user_id):
    """Edit a user/team."""
    user = db.session.get(User, user_id)
    if user is None:
        flash("User not found.", "error")
        return redirect(url_for("admin.users.index"))

    if request.method == "POST":
        team_name = request.form["team_name"]
        short_team_name = request.form["short_team_name"]
        tiebreaker_order = request.form["tiebreaker_order"]
        slack_id = request.form.get("slack_id", "")
        discord_id = request.form.get("discord_id", "")
        is_league_manager = request.form.get("is_league_manager") == "on"

        error = None

        if not team_name:
            error = "Team name is required."
        elif not short_team_name:
            error = "Short team name is required."
        elif not tiebreaker_order:
            error = "Tiebreaker order is required."

        try:
            tiebreaker_order = int(tiebreaker_order)
        except ValueError:
            error = "Tiebreaker order must be a number."

        if error:
            flash(error, "error")
        else:
            # Track changes for audit log
            changes = {}

            if user.team_name != team_name:
                changes['team_name'] = {'old': user.team_name, 'new': team_name}

            if user.short_team_name != short_team_name:
                changes['short_team_name'] = {'old': user.short_team_name, 'new': short_team_name}

            if user.tiebreaker_order != tiebreaker_order:
                changes['tiebreaker_order'] = {'old': user.tiebreaker_order, 'new': tiebreaker_order}

            if user.slack_id != slack_id:
                changes['slack_id'] = {'old': user.slack_id, 'new': slack_id}

            if user.discord_id != discord_id:
                changes['discord_id'] = {'old': user.discord_id, 'new': discord_id}

            if user.is_league_manager != is_league_manager:
                changes['is_league_manager'] = {'old': user.is_league_manager, 'new': is_league_manager}

            # Apply changes
            user.team_name = team_name
            user.short_team_name = short_team_name
            user.tiebreaker_order = tiebreaker_order
            user.slack_id = slack_id
            user.discord_id = discord_id
            user.is_league_manager = is_league_manager

            # Log audit event if there were changes
            if changes:
                change_desc = ", ".join([f"{k}: {v['old']} → {v['new']}" for k, v in changes.items()])
                description = f"Updated user {user.team_name}: {change_desc}"

                old_values = {k: v['old'] for k, v in changes.items()}
                new_values = {k: v['new'] for k, v in changes.items()}

                log_audit(
                    action='update',
                    entity_type='user',
                    entity_id=user.id,
                    description=description,
                    old_values=old_values,
                    new_values=new_values,
                    is_sensitive=False,
                    user=g.user
                )

            db.session.commit()
            flash(f"User '{user.team_name}' updated successfully.", "success")
            return redirect(url_for("admin.users.index"))

    return render_template("users/edit.html", user=user)
