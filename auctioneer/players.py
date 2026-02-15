import os
import tempfile
from flask import Blueprint, flash, g, redirect, render_template, request, url_for
from werkzeug.utils import secure_filename

from . import db
from .audit_log import log_admin_player_edit, log_csv_import
from .auth import admin_required, login_required
from .constants import TEAMS
from .model import Bid, Nomination, Player, User
from .utils import players_from_fantrax_export

bp = Blueprint("players", __name__, url_prefix="/players")


@bp.route("/")
@login_required
@admin_required
def index():
    players = (
        db.session.execute(db.select(Player).order_by(Player.name)).scalars().all()
    )
    users = db.session.execute(db.select(User)).scalars().all()

    return render_template("players/index.html", players=players, users=users)


@bp.route("/<int:player_id>/edit/", methods=["GET", "POST"])
@login_required
@admin_required
def edit(player_id):
    player = db.session.execute(
        db.select(Player).where(Player.id == player_id)
    ).scalar()
    users = db.session.execute(db.select(User).order_by(User.team_name)).scalars().all()

    if request.method == "POST":
        manager_id = request.form["manager_id"] or None
        matcher_id = request.form["matcher_id"] or None
        team = request.form["team"]
        hometown_discount = request.form.get("hometown_discount") == "on"

        error = None

        user_ids = [str(user.id) for user in users]
        if manager_id is not None and manager_id not in user_ids:
            error = "Status is invalid."
        if matcher_id is not None and matcher_id not in user_ids:
            error = "Match rights user ID is invalid."
        if team not in TEAMS:
            error = "MLB team is invalid."

        if error:
            flash(error)
        else:
            # Track changes for audit log
            changes = {}
            if player.manager_id != manager_id:
                manager_old = User.query.get(player.manager_id).team_name if player.manager_id else None
                manager_new = User.query.get(manager_id).team_name if manager_id else None
                changes['manager'] = {'old': manager_old, 'new': manager_new}

            if player.matcher_id != matcher_id:
                matcher_old = User.query.get(player.matcher_id).team_name if player.matcher_id else None
                matcher_new = User.query.get(matcher_id).team_name if matcher_id else None
                changes['matcher'] = {'old': matcher_old, 'new': matcher_new}

            if player.team != team:
                changes['team'] = {'old': player.team, 'new': team}

            if player.hometown_discount != hometown_discount:
                changes['hometown_discount'] = {'old': player.hometown_discount, 'new': hometown_discount}

            # Apply changes
            player.manager_id = manager_id
            player.matcher_id = matcher_id
            player.team = team
            player.hometown_discount = hometown_discount

            # Log audit event if there were changes
            if changes:
                log_admin_player_edit(player, changes, user=g.user)

            db.session.commit()
            return redirect(url_for("admin.players.index"))

    return render_template("players/edit.html", player=player, users=users, teams=TEAMS)


@bp.route("/import/", methods=["GET", "POST"])
@login_required
@admin_required
def import_players():
    """Import players from CSV file."""
    if request.method == "POST":
        # Check if file was uploaded
        if "file" not in request.files:
            flash("No file uploaded.", "error")
            return redirect(request.url)

        file = request.files["file"]

        if file.filename == "":
            flash("No file selected.", "error")
            return redirect(request.url)

        # Validate file type
        if not file.filename.endswith(".csv"):
            flash("File must be a CSV.", "error")
            return redirect(request.url)

        try:
            # Save to temporary file
            temp_fd, temp_path = tempfile.mkstemp(suffix=".csv")
            os.close(temp_fd)  # Close the file descriptor
            file.save(temp_path)

            # Get all users for matcher assignment
            users = db.session.execute(db.select(User)).scalars().all()

            # Parse CSV and create player objects
            new_players = players_from_fantrax_export(temp_path, users)

            # Delete all existing data (in order of foreign key dependencies)
            # First delete bids (they reference nominations)
            db.session.query(Bid).delete()
            # Then delete nominations (they reference players)
            db.session.query(Nomination).delete()
            # Finally delete players
            db.session.query(Player).delete()

            # Add new players
            db.session.add_all(new_players)

            # Log audit event
            log_csv_import(len(new_players), user=g.user)

            db.session.commit()

            # Clean up temp file
            os.unlink(temp_path)

            flash(f"Successfully imported {len(new_players)} players.", "success")
            return redirect(url_for("admin.players.index"))

        except Exception as e:
            db.session.rollback()
            flash(f"Error importing players: {str(e)}", "error")
            # Clean up temp file if it exists
            if os.path.exists(temp_path):
                os.unlink(temp_path)
            return redirect(request.url)

    return render_template("players/import.html")
