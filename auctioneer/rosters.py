from flask import Blueprint, g, redirect, render_template, url_for

from . import db
from .model import Player, User

bp = Blueprint("rosters", __name__, url_prefix="/rosters")

# TODO: Store this in some sort of config or DB table
SALARY_CAP = {
    2025: 1125,
    2026: 1170,
    2027: 1217,
    2028: 1265,
    2029: 1316,
    2030: 1369,
    2031: 1423,
    2032: 1480,
    2033: 1539,
    2034: 1601,
}


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

    team_salary = {year: {"salary": 0, "players": 0} for year in SALARY_CAP}
    min_year = list(SALARY_CAP.keys())[0]
    max_year = list(SALARY_CAP.keys())[-1]
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
        salary_cap=SALARY_CAP,
        team_salary=team_salary,
    )
