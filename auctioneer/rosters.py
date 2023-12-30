from flask import Blueprint, g, redirect, render_template, url_for

from . import db
from .model import Player

bp = Blueprint("rosters", __name__, url_prefix="/rosters")

# TODO: Store this in some sort of config or DB table
SALARY_CAP = {
    2024: 1082,
    2025: 1125,
    2026: 1170,
    2027: 1217,
    2028: 1265,
    2029: 1316,
    2030: 1369,
    2031: 1423,
    2032: 1480,
    2033: 1539,
}


@bp.route("/")
def index():
    if g.user:
        team = g.user.team.lower()
    else:
        teams = (
            db.session.execute(
                db.select(Player.status)
                .where(Player.status != "FA")
                .order_by(Player.status)
            )
            .scalars()
            .unique()
            .all()
        )
        team = teams[0]
    return redirect(url_for("rosters.roster", team=team.lower()))


@bp.route("/<string:team>/")
def roster(team):
    teams = (
        db.session.execute(
            db.select(Player.status)
            .where(Player.status != "FA")
            .order_by(Player.status)
        )
        .scalars()
        .unique()
        .all()
    )
    players = (
        db.session.execute(
            db.select(Player).where(Player.status == team.upper())
            # .order_by(Player.contract)
            .order_by(db.sql.desc(Player.salary))
        )
        .scalars()
        .all()
    )

    team_salary = {year: 0 for year in SALARY_CAP}
    min_year = list(SALARY_CAP.keys())[0]
    max_year = list(SALARY_CAP.keys())[-1]
    for player in players:
        if player.contract is None:
            continue
        year = min_year
        while year <= player.contract and year <= max_year:
            team_salary[year] += player.salary
            year += 1

    return render_template(
        "rosters/roster.html",
        selected_team=team,
        players=players,
        teams=teams,
        salary_cap=SALARY_CAP,
        team_salary=team_salary,
    )
