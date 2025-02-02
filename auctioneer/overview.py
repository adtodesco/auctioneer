from flask import Blueprint, render_template

bp = Blueprint("overview", __name__, url_prefix="/overview")


@bp.route("/")
def index():
    return render_template("overview/index.html")
