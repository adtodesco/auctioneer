from datetime import datetime, timedelta

import pytz
from flask import Blueprint, flash, g, redirect, render_template, request, url_for

from auctioneer.notifications import (
    add_auctions_close_notification,
    add_nomination_period_begun_notification,
    add_nomination_period_end_notification,
    remove_auctions_close_notification,
    remove_nomination_period_begun_notification,
    remove_nomination_period_end_notification,
)

from . import db
from .audit_log import log_slot_create, log_slot_delete, log_slot_update
from .auth import admin_required, login_required
from .model import Slot
from .utils import group_slots_by_round

bp = Blueprint("slots", __name__, url_prefix="/slots")


@bp.route("/")
@login_required
@admin_required
def index():
    slots = db.session.execute(db.select(Slot).order_by(Slot.round)).scalars().all()
    rounds = group_slots_by_round(slots)
    return render_template("slots/index.html", rounds=rounds)


@bp.route("/create/", methods=["GET", "POST"])
@login_required
@admin_required
def create():
    if request.method == "POST":
        round_num = request.form["round_num"]
        round_start_date = request.form["round_start_date"]
        round_start_time = request.form["round_start_time"]
        nomination_opens_at_date = request.form["nomination_opens_at_date"]
        nomination_opens_at_time = request.form["nomination_opens_at_time"]
        nomination_closes_at_date = request.form["nomination_closes_at_date"]
        nomination_closes_at_time = request.form["nomination_closes_at_time"]
        num_slots = request.form["num_slots"]
        slot_timedelta = request.form["slot_timedelta"]

        error = None

        if not round_num:
            error = "Round number is required."
        elif not round_start_date:
            error = "Round start date is required."
        elif not round_start_time:
            error = "Round start time is required."
        elif not nomination_opens_at_date:
            error = "Nomination period open date is required."
        elif not nomination_opens_at_time:
            error = "Nomination period open time is required."
        elif not nomination_closes_at_date:
            error = "Nomination period close date is required."
        elif not nomination_closes_at_time:
            error = "Nomination period close time is required."
        elif not num_slots:
            error = "Number of slots is required."
        elif not slot_timedelta:
            error = "Time between slots is required."

        try:
            round_num = int(round_num)
        except TypeError:
            error = "Round number must be an integer."
        try:
            num_slots = int(num_slots)
        except TypeError:
            error = "Number of slots must be an integer."
        try:
            slot_timedelta = int(slot_timedelta)
        except TypeError:
            error = "Time between slots must be an integer."

        rounds = db.session.execute(db.select(Slot.round)).scalars().unique()
        if round_num in rounds:
            error = f"Round {round_num} already exists."

        if error:
            flash(error)
        else:
            utc = pytz.utc
            eastern = pytz.timezone("US/Eastern")

            nomination_opens_at = datetime.strptime(
                nomination_opens_at_date + " " + nomination_opens_at_time,
                "%Y-%m-%d %H:%M",
            )
            nomination_opens_at = eastern.localize(nomination_opens_at)
            nomination_opens_at = nomination_opens_at.astimezone(utc)

            nomination_closes_at = datetime.strptime(
                nomination_closes_at_date + " " + nomination_closes_at_time,
                "%Y-%m-%d %H:%M",
            )
            nomination_closes_at = eastern.localize(nomination_closes_at)
            nomination_closes_at = nomination_closes_at.astimezone(utc)

            closes_at = datetime.strptime(
                round_start_date + " " + round_start_time,
                "%Y-%m-%d %H:%M",
            )
            closes_at = eastern.localize(closes_at)
            closes_at = closes_at.astimezone(utc)

            slot_timedelta = timedelta(minutes=slot_timedelta)

            slots = list()
            for _ in range(num_slots):
                slots.append(
                    Slot(
                        round=round_num,
                        nomination_opens_at=nomination_opens_at,
                        nomination_closes_at=nomination_closes_at,
                        closes_at=closes_at,
                    )
                )
                closes_at += slot_timedelta

            db.session.add_all(slots)

            # Log audit events for slot creation
            for slot in slots:
                log_slot_create(slot, user=g.user)

            db.session.commit()

            add_nomination_period_begun_notification(
                round_num,
                nomination_opens_at,
                nomination_closes_at,
            )
            add_nomination_period_end_notification(round_num, nomination_closes_at)
            add_auctions_close_notification(round_num, slots[0].closes_at)

            return redirect(url_for("admin.slots.index"))

    return render_template("slots/create.html")


@bp.route("/<int:round>/edit/", methods=["GET", "POST"])
@login_required
@admin_required
def edit(round):
    slots = (
        db.session.execute(db.select(Slot).where(Slot.round == round)).scalars().all()
    )
    if request.method == "POST":
        round_num = request.form["round_num"]
        action = request.form["action"]

        if action.lower() == "delete":
            closed_slots = (
                db.session.execute(
                    db.select(Slot)
                    .where(Slot.round == round)
                    .where(Slot.closes_at < datetime.utcnow())
                )
                .scalars()
                .all()
            )
            if closed_slots:
                flash(
                    f"Unable to delete {len(closed_slots)} slots from round {round} "
                    "because they are already closed."
                )

            # Get slots to delete for audit logging
            slots_to_delete = (
                db.session.execute(
                    db.select(Slot)
                    .where(Slot.round == round)
                    .where(Slot.closes_at > datetime.utcnow())
                )
                .scalars()
                .all()
            )

            # Log audit events for slot deletion
            for slot in slots_to_delete:
                log_slot_delete(slot, user=g.user)

            db.session.query(Slot).where(Slot.round == round).where(
                Slot.closes_at > datetime.utcnow()
            ).delete()
            db.session.commit()

            remove_nomination_period_begun_notification(round)
            remove_nomination_period_end_notification(round)
            remove_auctions_close_notification(round)

            return redirect(url_for("admin.slots.index"))
        else:
            error = None
            if not round_num:
                error = "Round number is required."

            try:
                round_num = int(round_num)
            except TypeError:
                error = "Round number must be an integer."

            rounds = db.session.execute(db.select(Slot.round)).scalars().unique()
            if round_num in rounds:
                error = f"Round {round_num} already exists."

            if error:
                flash(error)
            elif round_num != round:
                # Log audit events for slot updates
                for slot in slots:
                    old_values = {
                        'round': slot.round,
                        'closes_at': str(slot.closes_at),
                        'nomination_opens_at': str(slot.nomination_opens_at),
                        'nomination_closes_at': str(slot.nomination_closes_at)
                    }
                    slot.round = round_num
                    log_slot_update(slot, old_values, user=g.user)

                db.session.add_all(slots)
                db.session.commit()
                return redirect(url_for("admin.slots.index"))

    return render_template("slots/edit.html", round=round, slots=slots)


@bp.route("/<int:round>/delete/", methods=["POST"])
@login_required
@admin_required
def delete(round):
    closed_slots = db.session.execute(
        db.select(Slot)
        .where(Slot.round == round)
        .where(Slot.closes_at < datetime.utcnow())
    ).scalars.all()
    if closed_slots:
        flash(
            f"Unable to delete {len(closed_slots)} slots from round {round} because "
            "they are already closed."
        )

    db.session.query(Slot).where(Slot.round == round).where(
        Slot.closes_at > datetime.utcnow()
    ).delete()
    db.session.commit()

    return redirect(url_for("admin.slots.index"))
