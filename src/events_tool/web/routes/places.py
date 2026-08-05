from __future__ import annotations

from datetime import datetime, timezone

from flask import Blueprint, flash, redirect, render_template, request, url_for

from events_tool import places as places_mod
from events_tool.models import Place
from events_tool.web import get_store
from events_tool.web.auth import login_required

bp = Blueprint("places", __name__, url_prefix="/places")


@bp.route("/")
@login_required
def places_list():
    store = get_store()
    list_filter = request.args.get("list") or None
    rows = store.places(list_name=list_filter)
    list_names = sorted({r["list_name"] for r in store.places()})
    return render_template("places.html", places=rows, list_names=list_names, active_list=list_filter)


@bp.route("/import", methods=["POST"])
@login_required
def import_places():
    store = get_store()
    file = request.files.get("file")
    list_name = request.form.get("list_name", "").strip()

    if not file or not file.filename:
        flash("Choose a KML or CSV file first.", "error")
        return redirect(url_for("places.places_list"))
    if not list_name:
        flash("Give this list a name.", "error")
        return redirect(url_for("places.places_list"))

    file_format = "kml" if file.filename.lower().endswith(".kml") else "csv"
    text = file.read().decode("utf-8", errors="replace")

    try:
        raw_places = places_mod.parse_places_file(text, file_format)
    except Exception as exc:  # noqa: BLE001 - surfaced to the user
        flash(f"Couldn't parse that file: {exc}", "error")
        return redirect(url_for("places.places_list"))

    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for rp in raw_places:
        store.insert_place(
            Place(
                id=None, name=rp.name, address=rp.address, lat=rp.lat, lon=rp.lon,
                tags=rp.tags, url=rp.url, list_name=list_name, source=file_format, imported_at=now,
            )
        )
    flash(f"Imported {len(raw_places)} place(s) into '{list_name}'.", "success")
    return redirect(url_for("places.places_list"))
