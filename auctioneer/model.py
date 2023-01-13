from . import db


class User(db.Model):
    __tablename__ = "user"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String, unique=True, index=True, nullable=False)
    password = db.Column(db.String, nullable=False)
    is_league_manager = db.Column(db.Boolean, nullable=False, default=False)
    tiebreaker_order = db.Column(db.Integer, unique=True)

    # One-to-many relationships
    bids = db.relationship("Bid", back_populates="user")

    def __repr__(self):
        return "<User {}>".format(self.username)


class Slot(db.Model):
    __tablename__ = "slot"

    id = db.Column(db.Integer, primary_key=True)
    block = db.Column(db.Integer)
    ends_at = db.Column(db.DateTime, nullable=False)

    # One-to-one relationships
    nomination = db.relationship("Nomination", back_populates="slot")


class Nomination(db.Model):
    __tablename__ = "nomination"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String, nullable=False)
    position = db.Column(db.String, nullable=False)
    team = db.Column(db.String, nullable=False)
    slot_id = db.Column(
        db.Integer, db.ForeignKey("slot.id"), unique=True, nullable=False
    )
    nominator_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    matcher_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    winner_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    created_at = db.Column(db.DateTime, nullable=False, server_default=db.func.now())

    # One-to-one relationships
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
