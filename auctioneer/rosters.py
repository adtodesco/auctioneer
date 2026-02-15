from flask import Blueprint, flash, g, redirect, render_template, url_for

from . import db
from .config import get_salary_cap
from .model import Player, User

bp = Blueprint("rosters", __name__, url_prefix="/rosters")


@bp.route("/")
def index():
    if g.user:
        short_team_name = g.user.short_team_name.lower()
    else:
        short_team_names = (
            db.session.execute(
                db.select(User.short_team_name).order_by(User.short_team_name)
            )
            .scalars()
            .all()
        )
        short_team_name = short_team_names[0]
    return redirect(url_for("rosters.roster", team=short_team_name.lower()))


@bp.route("/<string:team>/")
def roster(team):
    user = db.session.execute(
        db.select(User).where(User.short_team_name == team.upper())
    ).scalar()

    players = (
        db.session.execute(
            db.select(Player)
            .join(User, Player.manager_id == User.id)
            .where(User.short_team_name == team.upper())
            .order_by(db.sql.expression.nullsfirst(db.sql.desc(Player.salary)))
            .order_by(Player.contract.desc())
        )
        .scalars()
        .all()
    )

    short_team_names = (
        db.session.execute(
            db.select(User.short_team_name).order_by(User.short_team_name)
        )
        .scalars()
        .all()
    )

    salary_cap = get_salary_cap()

    # Check if salary cap is configured
    if not salary_cap:
        flash("Salary cap is not configured. Please ask the league manager to configure it.", "error")
        # Show empty roster state
        team_salary = {}
        min_year = None
        max_year = None
    else:
        team_salary = {year: {"salary": 0, "players": 0} for year in salary_cap}
        min_year = min(salary_cap.keys())
        max_year = max(salary_cap.keys())
    # Only calculate salary if config is set
    if min_year is not None and max_year is not None:
        for player in players:
            if player.contract is None:
                continue
            year = min_year
            while year <= player.contract and year <= max_year:
                team_salary[year]["salary"] += player.salary
                team_salary[year]["players"] += 1
                year += 1

    return render_template(
        "rosters/roster.html",
        selected_user=user,
        players=players,
        teams=short_team_names,
        salary_cap=salary_cap,
        team_salary=team_salary,
    )
