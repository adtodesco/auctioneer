from flask import Blueprint, current_app, send_from_directory

bp = Blueprint("static", __name__, url_prefix="/static")


@bp.route("/<path:filename>")
def staticfiles(filename):
    return send_from_directory(current_app.config["STATIC_FOLDER"], filename)
