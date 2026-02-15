"""Audit log viewer blueprint and logging utilities."""

import json
from flask import Blueprint, g, render_template, request
from sqlalchemy import desc

from . import db
from .auth import admin_required, login_required
from .model import AuditLog, User


bp = Blueprint("audit_log", __name__, url_prefix="/audit")


@bp.route("/")
@login_required
@admin_required
def index():
    """View audit log with filters."""
    # Get filter parameters
    show_sensitive = request.args.get('show_sensitive', 'false') == 'true'
    entity_type = request.args.get('entity_type', '')
    user_id = request.args.get('user_id', '')
    page = int(request.args.get('page', 1))
    per_page = 50

    # Build query
    query = db.select(AuditLog).order_by(desc(AuditLog.created_at))

    # Apply filters
    if entity_type:
        query = query.where(AuditLog.entity_type == entity_type)
    if user_id:
        query = query.where(AuditLog.user_id == int(user_id))
    if not show_sensitive:
        query = query.where(AuditLog.is_sensitive == False)

    # Paginate
    total_query = db.select(db.func.count()).select_from(AuditLog)
    if entity_type:
        total_query = total_query.where(AuditLog.entity_type == entity_type)
    if user_id:
        total_query = total_query.where(AuditLog.user_id == int(user_id))
    if not show_sensitive:
        total_query = total_query.where(AuditLog.is_sensitive == False)

    total = db.session.execute(total_query).scalar()
    total_pages = max(1, (total + per_page - 1) // per_page)

    query = query.limit(per_page).offset((page - 1) * per_page)
    audit_entries = db.session.execute(query).scalars().all()

    # Get all users for filter dropdown
    users = db.session.execute(db.select(User).order_by(User.team_name)).scalars().all()

    # Get distinct entity types for filter
    entity_types_query = db.select(AuditLog.entity_type).distinct().order_by(AuditLog.entity_type)
    entity_types = [row[0] for row in db.session.execute(entity_types_query)]

    return render_template(
        "audit_log/index.html",
        audit_entries=audit_entries,
        users=users,
        entity_types=entity_types,
        show_sensitive=show_sensitive,
        selected_entity_type=entity_type,
        selected_user_id=user_id,
        page=page,
        total_pages=total_pages,
        total=total
    )


# Audit logging helper functions

def log_audit(
    action,
    entity_type,
    entity_id,
    description,
    old_values=None,
    new_values=None,
    is_sensitive=False,
    user=None
):
    """Log an audit event.

    Args:
        action: 'create', 'update', 'delete'
        entity_type: 'player', 'nomination', 'bid', 'config', etc.
        entity_id: ID of the entity
        description: Human-readable description
        old_values: Dict of old values (will be JSON encoded)
        new_values: Dict of new values (will be JSON encoded)
        is_sensitive: Whether this should be hidden by default in UI
        user: User object (defaults to g.user if available)
    """
    if user is None:
        user = getattr(g, 'user', None)

    user_id = user.id if user else None
    ip_address = request.remote_addr if request else None

    audit_entry = AuditLog(
        user_id=user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        description=description,
        old_values=json.dumps(old_values) if old_values else None,
        new_values=json.dumps(new_values) if new_values else None,
        is_sensitive=is_sensitive,
        ip_address=ip_address
    )

    db.session.add(audit_entry)
    # Note: Caller is responsible for committing


def log_player_update(player, old_values, new_values, user=None):
    """Log a player update."""
    description = f"Updated player {player.name}"
    log_audit(
        action='update',
        entity_type='player',
        entity_id=player.id,
        description=description,
        old_values=old_values,
        new_values=new_values,
        is_sensitive=False,
        user=user
    )


def log_bid(nomination, user, old_value, new_value):
    """Log a bid update (sensitive)."""
    if old_value is None:
        description = f"{user.team_name} placed bid of ${new_value} on {nomination.player.name}"
    elif new_value is None:
        description = f"{user.team_name} removed bid on {nomination.player.name}"
    else:
        description = f"{user.team_name} updated bid on {nomination.player.name}"

    log_audit(
        action='update',
        entity_type='bid',
        entity_id=nomination.id,
        description=description,
        old_values={'value': old_value} if old_value else None,
        new_values={'value': new_value} if new_value else None,
        is_sensitive=True,  # Bids are sensitive during auction
        user=user
    )


def log_nomination(nomination, user=None):
    """Log a nomination creation (sensitive - includes bid value)."""
    description = f"{nomination.nominator_user.team_name} nominated {nomination.player.name}"
    log_audit(
        action='create',
        entity_type='nomination',
        entity_id=nomination.id,
        description=description,
        new_values={
            'player': nomination.player.name,
            'slot_id': nomination.slot_id
        },
        is_sensitive=True,
        user=user or nomination.nominator_user
    )


def log_match_decision(nomination, accepted, user=None):
    """Log a match decision (sensitive until resolved)."""
    action_text = "accepted" if accepted else "declined"
    description = f"{nomination.player.matcher_user.team_name} {action_text} match for {nomination.player.name}"

    log_audit(
        action='update',
        entity_type='match',
        entity_id=nomination.id,
        description=description,
        new_values={'accepted': accepted},
        is_sensitive=True,  # Match decisions are sensitive
        user=user
    )


def log_player_signed(player, contract, salary, user=None):
    """Log a player signing."""
    description = f"{player.manager_user.team_name} signed {player.name} to {contract}-year contract at ${salary}/year"
    log_audit(
        action='update',
        entity_type='player',
        entity_id=player.id,
        description=description,
        new_values={
            'contract': contract,
            'salary': salary
        },
        is_sensitive=False,  # Signings are public
        user=user
    )


def log_config_change(key, old_value, new_value, user=None):
    """Log a config change."""
    description = f"Updated config: {key}"
    log_audit(
        action='update',
        entity_type='config',
        entity_id=None,
        description=description,
        old_values={'value': old_value},
        new_values={'value': new_value},
        is_sensitive=False,
        user=user
    )


def log_csv_import(player_count, user=None):
    """Log a CSV import."""
    description = f"Imported {player_count} players from CSV"
    log_audit(
        action='create',
        entity_type='import',
        entity_id=None,
        description=description,
        new_values={'player_count': player_count},
        is_sensitive=False,
        user=user
    )


def log_tiebreaker_update(user_id, old_order, new_order, admin_user=None):
    """Log a tiebreaker order update."""
    from .model import User
    user = User.query.get(user_id)
    description = f"Updated tiebreaker order for {user.team_name}: {old_order} → {new_order}"
    log_audit(
        action='update',
        entity_type='tiebreaker',
        entity_id=user_id,
        description=description,
        old_values={'order': old_order},
        new_values={'order': new_order},
        is_sensitive=False,
        user=admin_user
    )


def log_slot_create(slot, user=None):
    """Log a slot creation."""
    description = f"Created slot for round {slot.round}"
    log_audit(
        action='create',
        entity_type='slot',
        entity_id=slot.id,
        description=description,
        new_values={
            'round': slot.round,
            'closes_at': str(slot.closes_at),
            'nomination_opens_at': str(slot.nomination_opens_at),
            'nomination_closes_at': str(slot.nomination_closes_at)
        },
        is_sensitive=False,
        user=user
    )


def log_slot_update(slot, old_values, user=None):
    """Log a slot update."""
    description = f"Updated slot for round {slot.round}"
    log_audit(
        action='update',
        entity_type='slot',
        entity_id=slot.id,
        description=description,
        old_values=old_values,
        new_values={
            'round': slot.round,
            'closes_at': str(slot.closes_at),
            'nomination_opens_at': str(slot.nomination_opens_at),
            'nomination_closes_at': str(slot.nomination_closes_at)
        },
        is_sensitive=False,
        user=user
    )


def log_slot_delete(slot, user=None):
    """Log a slot deletion."""
    description = f"Deleted slot for round {slot.round}"
    log_audit(
        action='delete',
        entity_type='slot',
        entity_id=slot.id,
        description=description,
        old_values={
            'round': slot.round,
            'closes_at': str(slot.closes_at)
        },
        is_sensitive=False,
        user=user
    )


def log_admin_player_edit(player, changes, user=None):
    """Log an admin player edit with specific field changes."""
    change_desc = ", ".join([f"{k}: {v['old']} → {v['new']}" for k, v in changes.items()])
    description = f"Admin updated {player.name}: {change_desc}"

    old_values = {k: v['old'] for k, v in changes.items()}
    new_values = {k: v['new'] for k, v in changes.items()}

    log_audit(
        action='update',
        entity_type='player',
        entity_id=player.id,
        description=description,
        old_values=old_values,
        new_values=new_values,
        is_sensitive=False,
        user=user
    )


def log_admin_player_sign(player, manager, contract, salary, user=None):
    """Log an admin signing a player on behalf of a manager."""
    description = f"Admin signed {player.name} to {manager.team_name}: {contract}-year contract at ${salary}/year"
    log_audit(
        action='update',
        entity_type='player',
        entity_id=player.id,
        description=description,
        new_values={
            'manager': manager.team_name,
            'contract': contract,
            'salary': salary
        },
        is_sensitive=False,
        user=user
    )


def log_nomination_edit(nomination, changes, user=None):
    """Log a nomination edit."""
    change_desc = ", ".join([f"{k}: {v['old']} → {v['new']}" for k, v in changes.items()])
    description = f"Admin updated nomination for {nomination.player.name}: {change_desc}"

    old_values = {k: v['old'] for k, v in changes.items()}
    new_values = {k: v['new'] for k, v in changes.items()}

    log_audit(
        action='update',
        entity_type='nomination',
        entity_id=nomination.id,
        description=description,
        old_values=old_values,
        new_values=new_values,
        is_sensitive=False,
        user=user
    )
