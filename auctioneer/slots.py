from datetime import datetime, timedelta

from flask import Blueprint, flash, redirect, render_template, request, url_for

from auctioneer.auction import NOMINATION_DAY_RANGE, convert_slots_timezone
from auctioneer.slack import (
    add_auctions_close_notification,
    add_nomination_period_begun_notification,
    add_nomination_period_end_notification,
    remove_auctions_close_notification,
    remove_nomination_period_begun_notification,
    remove_nomination_period_end_notification,
)

from . import db
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
        start_date = request.form["start_date"]
        start_time = request.form["start_time"]
        num_slots = request.form["num_slots"]
        slot_timedelta = request.form["slot_timedelta"]

        error = None

        if not round_num:
            error = "Round number is required."
        elif not start_date:
            error = "Start date is required."
        elif not start_time:
            error = "Start time is required."
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
            slots = list()

            closes_at = start_date + " " + start_time
            closes_at = datetime.strptime(closes_at, "%Y-%m-%d %H:%M")
            slot_timedelta = timedelta(minutes=slot_timedelta)

            for _ in range(num_slots):
                slots.append(Slot(round=round_num, closes_at=closes_at))
                closes_at += slot_timedelta

            convert_slots_timezone(slots, from_tz="US/Eastern", to_tz="UTC")

            db.session.add_all(slots)
            db.session.commit()

            nominations_open_at = (
                slots[-1].closes_at
                - timedelta(days=NOMINATION_DAY_RANGE[0])
                + timedelta(minutes=1)
            )
            nominations_close_at = slots[0].closes_at - timedelta(
                days=NOMINATION_DAY_RANGE[1]
            )
            add_nomination_period_begun_notification(
                round_num,
                nominations_open_at,
                nominations_close_at,
            )
            add_nomination_period_end_notification(round_num, nominations_close_at)
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
                for slot in slots:
                    slot.round = round_num
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
