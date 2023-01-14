from datetime import datetime, timedelta

import click
from flask import current_app

from . import db
from .model import Nomination, Slot
from .utils import close_nomination


def init_db():
    from .model import Bid, Nomination, Player, Slot, User

    with current_app.app_context():
        db.drop_all()
        db.create_all()

    with current_app.open_resource("data/players.csv") as f:
        players = list(
            s.decode("utf-8").strip("\n").replace('"', "").split(",")
            for s in f.readlines()
        )

    rows = [
        Player(fantrax_id=player[0], name=player[1], team=player[2], position=player[3])
        for player in players
    ]
    db.session.add_all(rows)

    with current_app.open_resource("data/slots.csv") as f:
        slots = list(s.decode("utf-8").strip("\n").split(",") for s in f.readlines())

    rows = [
        Slot(block=slot[0], ends_at=datetime.strptime(slot[1], "%Y-%m-%d %H:%M:%S"))
        for slot in slots
    ]
    db.session.add_all(rows)
    db.session.commit()


@click.command("init-db")
def init_db_command():
    """Clear the existing data and create new tables."""
    init_db()
    click.echo("Initialized the database.")


def close_nominations():
    statement = (
        db.select(Nomination)
        .join(Slot)
        .where(Nomination.winner_id.is_(None))
        .where(
            ((Slot.ends_at < datetime.utcnow()) & Nomination.matcher_id.is_(None))
            | (
                (Slot.ends_at < datetime.utcnow() + timedelta(days=1))
                & (Nomination.matcher_id.is_not(None))
            )
        )
    )
    nominations = db.session.execute(statement).scalars().all()
    for nomination in nominations:
        close_nomination(nomination)

    return nominations


@click.command("close-nominations")
def close_nominations_command():
    """Close any open nominations passed the slot end and/or match end."""
    nominations = close_nominations()
    click.echo(f"Closed {len(nominations)} nominations.")
