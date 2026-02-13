from . import db


class User(db.Model):
    __tablename__ = "user"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String, unique=True, index=True)
    password = db.Column(db.String)
    team_name = db.Column(db.String, nullable=False)
    short_team_name = db.Column(db.String, nullable=False)
    tiebreaker_order = db.Column(db.Integer, unique=True)
    slack_id = db.Column(db.String)
    discord_id = db.Column(db.String)
    is_league_manager = db.Column(db.Boolean, nullable=False, default=False)

    # One-to-many relationships
    bids = db.relationship("Bid", back_populates="user")

    def __repr__(self):
        return f"<User {str(self)}>"

    def __str__(self):
        return self.username or self.team_name


class Player(db.Model):
    __tablename__ = "player"

    id = db.Column(db.Integer, primary_key=True)
    fantrax_id = db.Column(db.String, index=True, nullable=False, unique=True)
    name = db.Column(db.String, nullable=False)
    team = db.Column(db.String, nullable=False)
    position = db.Column(db.String, nullable=False)
    salary = db.Column(db.Integer, default=None)
    contract = db.Column(db.Integer, default=None)
    manager_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    matcher_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    hometown_discount = db.Column(db.Boolean, default=False, nullable=False)

    # One-to-one relationships
    nomination = db.relationship("Nomination", back_populates="player")
    manager_user = db.relationship("User", foreign_keys=manager_id)
    matcher_user = db.relationship("User", foreign_keys=matcher_id)


class Slot(db.Model):
    __tablename__ = "slot"

    id = db.Column(db.Integer, primary_key=True)
    round = db.Column(db.Integer)
    closes_at = db.Column(db.DateTime, nullable=False)
    nomination_opens_at = db.Column(db.DateTime, nullable=False)
    nomination_closes_at = db.Column(db.DateTime, nullable=False)

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
    created_at = db.Column(db.DateTime, nullable=False, server_default=db.func.now())

    # One-to-one relationships
    player = db.relationship("Player", back_populates="nomination")
    slot = db.relationship("Slot", back_populates="nomination")
    nominator_user = db.relationship("User", foreign_keys=nominator_id)

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


class Config(db.Model):
    __tablename__ = "config"

    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String, unique=True, nullable=False, index=True)
    value = db.Column(db.String, nullable=False)
    description = db.Column(db.String)
    value_type = db.Column(db.String, nullable=False)  # 'int', 'float', 'json'


class AuditLog(db.Model):
    __tablename__ = "audit_log"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    action = db.Column(db.String, nullable=False)  # 'create', 'update', 'delete'
    entity_type = db.Column(db.String, nullable=False, index=True)  # 'player', 'nomination', 'bid', etc.
    entity_id = db.Column(db.Integer, index=True)
    description = db.Column(db.String, nullable=False)  # Human-readable description
    old_values = db.Column(db.String)  # JSON of old values
    new_values = db.Column(db.String)  # JSON of new values
    is_sensitive = db.Column(db.Boolean, default=False, nullable=False)  # Hide by default in UI
    ip_address = db.Column(db.String)
    created_at = db.Column(db.DateTime, nullable=False, server_default=db.func.now(), index=True)

    # Relationship
    user = db.relationship("User", foreign_keys=user_id)
