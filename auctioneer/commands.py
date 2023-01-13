from datetime import datetime

import click
from flask import current_app

from . import db


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
