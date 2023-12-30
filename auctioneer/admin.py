from flask import Blueprint, render_template

from .auth import admin_required, login_required

bp = Blueprint("admin", __name__, url_prefix="/admin")


@bp.route("/")
@login_required
@admin_required
def index():
    return render_template("admin/index.html")
