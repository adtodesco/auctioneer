import logging
import os

from flask import Flask
from flask_moment import Moment
from flask_sqlalchemy import SQLAlchemy

moment = Moment()
db = SQLAlchemy()


def create_app(test_config=None):
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] %(levelname)s in %(module)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
    )

    # create and configure the app
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("SECRET_KEY", "dev"),
        SQLALCHEMY_DATABASE_URI="sqlite:///auctioneer.sqlite",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        STATIC_FOLDER=os.path.join(app.root_path, "/static"),
    )

    if test_config is None:
        # load the instance config, if it exists, when not testing
        app.config.from_pyfile("config.py", silent=True)
    else:
        # load the test config if passed in
        app.config.from_mapping(test_config)

    # ensure the instance folder exists
    try:
        os.makedirs(app.instance_path)
    except OSError:
        pass

    moment.init_app(app)

    db.init_app(app)

    # All models need to be imported before setting up the database
    from .model import Bid, Nomination, Notification, Player, Slot, User  # noqa: F401

    with app.app_context():
        db.create_all()

    from . import home

    app.register_blueprint(home.bp)

    from . import auth

    app.register_blueprint(auth.bp)

    from . import auction

    app.register_blueprint(auction.bp)

    from . import admin, slots

    admin.bp.register_blueprint(slots.bp)

    app.register_blueprint(admin.bp)

    from . import rosters

    app.register_blueprint(rosters.bp)

    from . import tiebreaker

    app.register_blueprint(tiebreaker.bp)

    from . import static

    app.register_blueprint(static.bp)

    from .commands import (
        close_nominations_command,
        init_db_command,
        send_notifications_command,
    )

    app.cli.add_command(init_db_command)
    app.cli.add_command(close_nominations_command)
    app.cli.add_command(send_notifications_command)

    return app
