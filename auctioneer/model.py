from . import db


class User(db.Model):
    __tablename__ = "user"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String, unique=True, index=True, nullable=False)
    password = db.Column(db.String, nullable=False)
    slack_id = db.Column(db.String, nullable=False)
    is_league_manager = db.Column(db.Boolean, nullable=False, default=False)
    tiebreaker_order = db.Column(db.Integer, unique=True)

    # One-to-many relationships
    bids = db.relationship("Bid", back_populates="user")

    def __repr__(self):
        return f"<User {self.username}>"


class Player(db.Model):
    __tablename__ = "player"

    id = db.Column(db.Integer, primary_key=True)
    fantrax_id = db.Column(db.String, index=True, nullable=False, unique=True)
    name = db.Column(db.String, nullable=False)
    team = db.Column(db.String, nullable=False)
    position = db.Column(db.String, nullable=False)
    status = db.Column(db.String, nullable=False)
    salary = db.Column(db.Integer, default=None)
    contract = db.Column(db.Integer, default=None)

    # One-to-one relationships
    nomination = db.relationship("Nomination", back_populates="player")


class Slot(db.Model):
    __tablename__ = "slot"

    id = db.Column(db.Integer, primary_key=True)
    block = db.Column(db.Integer)
    closes_at = db.Column(db.DateTime, nullable=False)

    # One-to-one relationships
    nomination = db.relationship("Nomination", back_populates="slot")


class Nomination(db.Model):
    __tablename__ = "nomination"

    id = db.Column(db.Integer, primary_key=True)
    player_id = db.Column(
        db.Integer, db.ForeignKey("player.id"), unique=True, nullable=False
    )
    slot_id = db.Column(
        db.Integer, db.ForeignKey("slot.id"), unique=True, nullable=False
    )
    nominator_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    matcher_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    winner_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    created_at = db.Column(db.DateTime, nullable=False, server_default=db.func.now())

    # One-to-one relationships
    player = db.relationship("Player", back_populates="nomination")
    slot = db.relationship("Slot", back_populates="nomination")
    nominator_user = db.relationship("User", foreign_keys=nominator_id)
    matcher_user = db.relationship("User", foreign_keys=matcher_id)
    winner_user = db.relationship("User", foreign_keys=winner_id)

    # One-to-many relationships
    bids = db.relationship(
        "Bid",
        back_populates="nomination",
        order_by="Bid.value.desc()",
        cascade="all, delete",
    )

    def __repr__(self):
        return f"<Nomination {str(self)}>"

    def __str__(self):
        return f"{self.player.name} ({self.player.position}, {self.player.team})"


class Bid(db.Model):
    __tablename__ = "bid"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    nomination_id = db.Column(
        db.Integer, db.ForeignKey("nomination.id"), nullable=False
    )
    value = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, nullable=False, server_default=db.func.now())

    # Many-to-one relationships
    user = db.relationship("User", back_populates="bids")
    nomination = db.relationship("Nomination", back_populates="bids")

    def __repr__(self):
        return f"<Bid {self.user.username} for {self.nomination.player.name}>"


class Notification(db.Model):
    __tablename__ = "notification"

    id = db.Column(db.Integer, primary_key=True)
    sent = db.Column(db.Boolean, nullable=False, default=False)
    title = db.Column(db.String)
    message = db.Column(db.String)
    send_at = db.Column(db.DateTime, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, server_default=db.func.now())
