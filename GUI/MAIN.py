from datetime import datetime, timedelta
import os
from urllib.parse import urlparse

from dotenv import load_dotenv
from flask import Flask, flash, jsonify, redirect, render_template, request, url_for

from backend import (
    app_release,
    color_search,
    data_manipulation,
    generate_barcode,
    log_data,
    order_links,
    settings_store,
    spreadsheet_stats,
    usage_analytics,
)
from backend.config import EMPTY_THRESHOLD, LOW_THRESHOLD
from backend.workbook_store import (
    get_inventory_roll,
    list_inventory_rows,
    toggle_inventory_favorite,
    update_inventory_roll,
)

load_dotenv()
app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev-secret-change-me")


def parse_float(value, field_name):
    if value is None or str(value).strip() == "":
        raise ValueError(f"{field_name} is required.")

    text = str(value).strip().replace(",", "")
    try:
        return float(text)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be a valid number.") from exc

def parse_timestamp(value):
    if value is None:
        return datetime.min
    if isinstance(value, datetime):
        return value

    text = str(value).strip()
    if not text:
        return datetime.min

    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return datetime.min


def parse_date(value):
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.strptime(text, "%Y-%m-%d")
    except ValueError:
        return None


def parse_optional_float(value, default=None):
    if value is None:
        return default

    text = str(value).strip().replace(",", "")
    if not text:
        return default

    try:
        return float(text)
    except ValueError:
        return default


def timestamp_now_iso():
    return datetime.now().replace(microsecond=0).isoformat()


def normalize_next_path(value):
    text = str(value or "").strip()
    if not text:
        return url_for("index")

    parsed = urlparse(text)
    if parsed.scheme or parsed.netloc:
        return url_for("index")
    if not text.startswith("/"):
        return url_for("index")
    if text.startswith("//"):
        return url_for("index")

    return text


def parse_roll_state(value):
    normalized = str(value or "").strip().lower()
    return normalized if normalized in ("new", "used") else "new"


def parse_int_setting(value, default, min_value, max_value):
    try:
        parsed = int(float(value))
    except (TypeError, ValueError):
        return default
    return max(min_value, min(max_value, parsed))


def parse_float_setting(value, default, min_value, max_value):
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return max(min_value, min(max_value, parsed))


def get_threshold_settings(app_settings):
    low_threshold = parse_float_setting(
        app_settings.get("low_threshold_g"), LOW_THRESHOLD, 0.0, 10000.0
    )
    empty_threshold = parse_float_setting(
        app_settings.get("empty_threshold_g"), EMPTY_THRESHOLD, 0.0, 1000.0
    )
    return low_threshold, empty_threshold


def get_scale_read_settings(app_settings):
    timeout_sec = parse_int_setting(app_settings.get("scale_timeout_sec"), 5, 1, 60)
    retry_count = parse_int_setting(app_settings.get("scale_retry_count"), 2, 1, 10)
    return timeout_sec, retry_count


def get_used_roll_map_settings(app_settings):
    fallback_level = str(app_settings.get("used_roll_map_fallback_level", "material")).strip().lower()
    min_samples = parse_int_setting(app_settings.get("used_roll_map_min_samples"), 1, 1, 1000)
    return fallback_level, min_samples


def get_inventory_rows():
    return list_inventory_rows()


def render_new_roll(step="info", **context):
    options = generate_barcode.get_catalog_options()
    app_settings = settings_store.load_settings()

    template_context = {
        "step": step,
        "brand_options": options["brands"],
        "color_options": options["colors"],
        "material_options": options["materials"],
        "attribute_options": options["attributes"],
        "location_options": options["locations"],
        "brand": "",
        "color": "",
        "material": "",
        "attribute_1": "",
        "attribute_2": "",
        "location": app_settings.get("default_location", "Lab"),
        "barcode": "",
        "scale_weight": "",
        "roll_state": parse_roll_state(app_settings.get("default_roll_condition", "new")),
        "mapped_roll_weight": None,
        "mapped_roll_weight_match": "",
    }
    template_context.update(context)
    return render_template("new_roll.html", **template_context)


@app.context_processor
def inject_app_settings():
    return {
        "app_settings": settings_store.load_settings(),
        "app_release": app_release.load_local_release_info(),
    }


def should_skip_onboarding_redirect():
    endpoint = request.endpoint or ""
    if request.method != "GET":
        return True
    if not endpoint:
        return True
    if endpoint == "static":
        return True
    if endpoint == "welcome":
        return True
    if request.path.startswith("/api/"):
        return True
    return False


@app.before_request
def enforce_onboarding():
    if should_skip_onboarding_redirect():
        return None

    app_settings = settings_store.load_settings()
    if app_settings.get("onboarding_completed", False):
        return None

    next_path = request.full_path if request.query_string else request.path
    next_path = str(next_path).rstrip("?")
    return redirect(url_for("welcome", next=next_path))


@app.route("/welcome", methods=["GET", "POST"])
def welcome():
    current = settings_store.load_settings()
    next_path = normalize_next_path(request.values.get("next", url_for("index")))

    if request.method == "POST":
        action = str(request.form.get("action", "save")).strip().lower()
        next_path = normalize_next_path(request.form.get("next", next_path))

        if action == "skip":
            settings_store.save_settings(
                {
                    "onboarding_completed": True,
                    "onboarding_completed_at": timestamp_now_iso(),
                }
            )
            flash("First-launch setup skipped. You can reopen it from Settings anytime.", "info")
            return redirect(next_path)

        updates = {
            "theme": request.form.get("theme", current.get("theme", "light")),
            "alert_mode": request.form.get("alert_mode", current.get("alert_mode", "all")),
            "rows_per_page": request.form.get("rows_per_page", current.get("rows_per_page", 20)),
            "default_location": request.form.get(
                "default_location", current.get("default_location", "Lab")
            ),
            "default_roll_condition": request.form.get(
                "default_roll_condition", current.get("default_roll_condition", "new")
            ),
            "filament_amount_g": request.form.get(
                "filament_amount_g", current.get("filament_amount_g", 1000.0)
            ),
            "low_threshold_g": request.form.get(
                "low_threshold_g", current.get("low_threshold_g", LOW_THRESHOLD)
            ),
            "empty_threshold_g": request.form.get(
                "empty_threshold_g", current.get("empty_threshold_g", EMPTY_THRESHOLD)
            ),
            "popular_weeks": request.form.get("popular_weeks", current.get("popular_weeks", 4)),
            "onboarding_completed": True,
            "onboarding_completed_at": timestamp_now_iso(),
        }
        settings_store.save_settings(updates)
        flash("First-launch setup saved.", "success")
        return redirect(next_path)

    return render_template(
        "welcome.html",
        settings=current,
        next_path=next_path,
        theme_options=settings_store.THEME_OPTIONS,
        alert_mode_options=settings_store.ALERT_MODE_OPTIONS,
        roll_condition_options=settings_store.ROLL_CONDITION_OPTIONS,
    )


@app.route("/")
def index():
    filaments = get_inventory_rows()
    filaments.sort(key=lambda row: parse_timestamp(row[0] if row else None), reverse=True)
    color_search_tokens = color_search.get_color_search_tokens_by_color()

    favorite_barcodes = [
        row[1]
        for row in filaments
        if row and len(row) > 12 and str(row[12]).strip().lower() == "true"
    ]

    return render_template(
        "index.html",
        filaments=filaments,
        total=len(filaments),
        favorite_barcodes=favorite_barcodes,
        color_search_tokens=color_search_tokens,
    )


@app.route("/popular")
def popular_filaments():
    app_settings = settings_store.load_settings()
    weeks_arg = request.args.get("weeks")
    group_by = str(request.args.get("group_by", "rolls")).strip().lower()
    if group_by not in ("rolls", "brand", "color", "brand_color"):
        group_by = "rolls"

    if weeks_arg is None or str(weeks_arg).strip() == "":
        default_weeks = int(app_settings.get("popular_weeks", 4))
        weeks = None if default_weeks <= 0 else default_weeks
    else:
        text = str(weeks_arg).strip().lower()
        if text == "all":
            weeks = None
        else:
            try:
                parsed = int(text)
            except ValueError:
                parsed = int(app_settings.get("popular_weeks", 4))
            weeks = None if parsed <= 0 else parsed

    selected_weeks = "all" if weeks is None else str(weeks)
    if group_by == "rolls":
        popular = spreadsheet_stats.get_most_popular_filaments(top_n=200, weeks=weeks)
        grouped = []
    else:
        grouped = spreadsheet_stats.get_most_popular_groups(
            top_n=200,
            weeks=weeks,
            group_by=group_by,
        )
        popular = []

    return render_template(
        "popular.html",
        filaments=popular,
        grouped=grouped,
        selected_weeks=selected_weeks,
        group_by=group_by,
    )


def resolve_usage_stats_request(args, app_settings, emit_flash=True):
    default_weeks = parse_int_setting(app_settings.get("popular_weeks"), 4, 0, 104)

    weeks_arg = str(args.get("weeks", "")).strip().lower()
    start_input = str(args.get("start", "")).strip()
    end_input = str(args.get("end", "")).strip()

    start_ts = None
    end_ts = None
    selected_weeks = "all"
    range_label = "All time"

    start_dt = parse_date(start_input) if start_input else None
    end_dt = parse_date(end_input) if end_input else None

    custom_range_requested = bool(start_input or end_input)
    if custom_range_requested:
        invalid_date = False
        if start_input and start_dt is None:
            if emit_flash:
                flash("Start date must be in YYYY-MM-DD format.", "error")
            invalid_date = True
        if end_input and end_dt is None:
            if emit_flash:
                flash("End date must be in YYYY-MM-DD format.", "error")
            invalid_date = True

        if not invalid_date:
            range_start = start_dt or end_dt
            range_end = end_dt or start_dt

            if range_start and range_end and range_start > range_end:
                range_start, range_end = range_end, range_start
                start_input = range_start.strftime("%Y-%m-%d")
                end_input = range_end.strftime("%Y-%m-%d")
                if emit_flash:
                    flash(
                        "Date range was normalized because start date was after end date.",
                        "warning",
                    )

            if range_start is not None:
                start_ts = range_start.strftime("%Y-%m-%d 00:00:00")
            if range_end is not None:
                end_ts = range_end.strftime("%Y-%m-%d 23:59:59")

            selected_weeks = "custom"
            if range_start and range_end and range_start.date() == range_end.date():
                range_label = range_start.strftime("%Y-%m-%d")
            else:
                start_label = range_start.strftime("%Y-%m-%d") if range_start else "Beginning"
                end_label = range_end.strftime("%Y-%m-%d") if range_end else "Now"
                range_label = f"{start_label} to {end_label}"

    if selected_weeks != "custom":
        if not weeks_arg:
            weeks = None if default_weeks <= 0 else default_weeks
        elif weeks_arg == "all":
            weeks = None
        else:
            parsed = parse_int_setting(
                weeks_arg,
                default_weeks if default_weeks > 0 else 4,
                0,
                104,
            )
            weeks = None if parsed <= 0 else parsed

        if weeks is None:
            selected_weeks = "all"
            range_label = "All time"
        else:
            selected_weeks = str(weeks)
            range_label = f"Last {weeks} week{'s' if weeks != 1 else ''}"
            start_ts = (datetime.now() - timedelta(weeks=weeks)).strftime("%Y-%m-%d %H:%M:%S")

    stats = usage_analytics.get_usage_summary(start_ts=start_ts, end_ts=end_ts)
    return {
        "stats": stats,
        "selected_weeks": selected_weeks,
        "start_input": start_input,
        "end_input": end_input,
        "range_label": range_label,
    }


@app.route("/usage_stats")
def usage_stats():
    app_settings = settings_store.load_settings()
    context = resolve_usage_stats_request(request.args, app_settings, emit_flash=True)
    return render_template("usage_stats.html", **context)


@app.route("/usage_stats/print")
def usage_stats_print():
    app_settings = settings_store.load_settings()
    context = resolve_usage_stats_request(request.args, app_settings, emit_flash=False)
    release = app_release.load_local_release_info()
    return render_template(
        "usage_stats_print.html",
        **context,
        generated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        app_version=release.get("version", ""),
    )


def normalize_stock_status_view(value):
    normalized = str(value or "").strip().lower()
    return normalized if normalized in ("low", "empty") else "low"


@app.route("/stock_status")
def stock_status():
    view = normalize_stock_status_view(request.args.get("view"))
    app_settings = settings_store.load_settings()
    low_threshold, empty_threshold = get_threshold_settings(app_settings)

    if view == "empty":
        rows = spreadsheet_stats.get_empty_rolls(empty_threshold=empty_threshold)
    else:
        rows = spreadsheet_stats.get_low_or_empty_filaments(
            low_threshold=low_threshold,
            empty_threshold=empty_threshold,
        )

    return render_template(
        "stock_status.html",
        view=view,
        rows=rows,
        low_threshold=low_threshold,
        empty_threshold=empty_threshold,
    )


@app.route("/low_empty")
def low_empty_filaments():
    return redirect(url_for("stock_status", view="low"))


@app.route("/empty_rolls")
def empty_rolls():
    return redirect(url_for("stock_status", view="empty"))


@app.route("/log", methods=["GET", "POST"])
def log_filament():
    form_data = {"barcode": "", "weight": ""}
    app_settings = settings_store.load_settings()
    low_threshold, empty_threshold = get_threshold_settings(app_settings)

    if request.method == "POST":
        barcode = request.form.get("barcode", "").strip()
        weight_text = request.form.get("weight", "").strip()
        form_data = {"barcode": barcode, "weight": weight_text}

        if not barcode:
            flash("Barcode is required.", "error")
            return render_template("log.html", form_data=form_data)

        try:
            measured_weight = parse_float(weight_text, "Current roll weight")
        except ValueError as exc:
            flash(str(exc), "error")
            return render_template("log.html", form_data=form_data)

        roll_weight_val = data_manipulation.get_roll_weight(barcode, None)

        if roll_weight_val is None:
            flash("Roll weight not found for this barcode.", "error")
            return render_template("log.html", form_data=form_data)

        filament_amount = round(measured_weight - float(roll_weight_val), 2)
        if filament_amount < 0:
            flash("Weight is below the recorded roll weight.", "error")
            return render_template("log.html", form_data=form_data)

        updated = log_data.log_filament_data_web(
            barcode=barcode,
            filament_amount=filament_amount,
            roll_weight=roll_weight_val,
            total_weight=measured_weight,
            source="web_log",
            empty_threshold=empty_threshold,
        )
        if not updated:
            flash("Barcode not found. Please add this roll first.", "error")
            return render_template("log.html", form_data=form_data)

        flash(f"Filament usage logged. Remaining amount: {filament_amount:.2f} g", "success")
        if app_settings.get("low_stock_alerts", True) and filament_amount < low_threshold:
            flash(
                f"Low-stock warning: this roll is under {low_threshold:.0f} g.",
                "warning",
            )
        return redirect(url_for("index"))

    return render_template("log.html", form_data=form_data)


@app.route("/api/scale_weight")
def api_scale_weight():
    app_settings = settings_store.load_settings()
    timeout_sec, retry_count = get_scale_read_settings(app_settings)
    weight = data_manipulation.read_scale_weight(timeout_sec=timeout_sec, retry_count=retry_count)
    if weight is None:
        return jsonify({"error": "Scale unavailable"}), 503
    return jsonify({"weight": round(float(weight), 2)})


@app.route("/api/update/check")
def api_update_check():
    timeout_sec = parse_int_setting(request.args.get("timeout_sec"), 4, 1, 20)
    status = app_release.check_for_updates(timeout_sec=timeout_sec)
    return jsonify(status), 200


@app.route("/new_roll", methods=["GET", "POST"])
def new_roll():
    app_settings = settings_store.load_settings()
    _, empty_threshold = get_threshold_settings(app_settings)
    scale_timeout_sec, scale_retry_count = get_scale_read_settings(app_settings)
    map_fallback_level, map_min_samples = get_used_roll_map_settings(app_settings)
    negative_filament_policy = str(app_settings.get("negative_filament_policy", "block")).strip().lower()
    if negative_filament_policy not in settings_store.NEGATIVE_FILAMENT_POLICY_OPTIONS:
        negative_filament_policy = "block"

    if request.method == "POST" and "step" not in request.form:
        brand = request.form.get("brand", "").strip()
        color = request.form.get("color", "").strip()
        material = request.form.get("material", "").strip()
        attr1 = request.form.get("attribute_1", "").strip()
        attr2 = request.form.get("attribute_2", "").strip()
        location = request.form.get("location", app_settings.get("default_location", "Lab")).strip()
        roll_state = parse_roll_state(
            request.form.get("roll_state", app_settings.get("default_roll_condition", "new"))
        )

        if not brand or not color or not material:
            flash("Brand, color, and material are required.", "error")
            return render_new_roll(
                step="info",
                brand=brand,
                color=color,
                material=material,
                attribute_1=attr1,
                attribute_2=attr2,
                location=location,
                roll_state=roll_state,
            )

        try:
            barcode = generate_barcode.generate_filament_barcode(
                brand=brand,
                color=color,
                material=material,
                attribute_1=attr1,
                attribute_2=attr2,
                location=location,
                sheet=None,
            )

            mapped_roll_weight = None
            mapped_roll_weight_match = ""
            if roll_state == "used":
                mapped_roll_weight, mapped_roll_weight_match = data_manipulation.get_roll_weight_from_map(
                    None,
                    brand=brand,
                    color=color,
                    material=material,
                    attribute_1=attr1,
                    attribute_2=attr2,
                    max_fallback_level=map_fallback_level,
                    min_samples=map_min_samples,
                )
        except ValueError as exc:
            flash(str(exc), "error")
            return render_new_roll(
                step="info",
                brand=brand,
                color=color,
                material=material,
                attribute_1=attr1,
                attribute_2=attr2,
                location=location,
                roll_state=roll_state,
            )

        if roll_state == "used" and mapped_roll_weight is None:
            flash(
                (
                    "No matching roll weight was found in weight_mapping.json for this used-roll profile. "
                    "Try relaxing fallback level or lowering min samples in Settings."
                ),
                "error",
            )
            return render_new_roll(
                step="info",
                brand=brand,
                color=color,
                material=material,
                attribute_1=attr1,
                attribute_2=attr2,
                location=location,
                roll_state=roll_state,
            )

        scale_weight = data_manipulation.read_scale_weight(
            timeout_sec=scale_timeout_sec,
            retry_count=scale_retry_count,
        )
        return render_new_roll(
            step="weight",
            barcode=barcode,
            brand=brand,
            color=color,
            material=material,
            attribute_1=attr1,
            attribute_2=attr2,
            location=location,
            scale_weight="" if scale_weight is None else f"{scale_weight:.2f}",
            roll_state=roll_state,
            mapped_roll_weight=mapped_roll_weight,
            mapped_roll_weight_match=mapped_roll_weight_match,
        )

    if request.method == "POST" and request.form.get("step") == "weight":
        brand = request.form.get("brand", "").strip()
        color = request.form.get("color", "").strip()
        material = request.form.get("material", "").strip()
        attr1 = request.form.get("attribute_1", "").strip()
        attr2 = request.form.get("attribute_2", "").strip()
        location = request.form.get("location", app_settings.get("default_location", "Lab")).strip()
        barcode = request.form.get("barcode", "").strip()
        weight_text = request.form.get("weight", "").strip()
        roll_state = parse_roll_state(
            request.form.get("roll_state", app_settings.get("default_roll_condition", "new"))
        )

        mapped_roll_weight = None
        mapped_roll_weight_match = ""
        if roll_state == "used":
            mapped_roll_weight, mapped_roll_weight_match = data_manipulation.get_roll_weight_from_map(
                None,
                brand=brand,
                color=color,
                material=material,
                attribute_1=attr1,
                attribute_2=attr2,
                max_fallback_level=map_fallback_level,
                min_samples=map_min_samples,
            )

        if not barcode:
            flash("Missing barcode. Please generate a barcode first.", "error")
            return render_new_roll(
                step="info",
                brand=brand,
                color=color,
                material=material,
                attribute_1=attr1,
                attribute_2=attr2,
                location=location,
                roll_state=roll_state,
            )

        try:
            starting_weight = parse_float(weight_text, "Starting weight")
        except ValueError as exc:
            flash(str(exc), "error")
            return render_new_roll(
                step="weight",
                barcode=barcode,
                brand=brand,
                color=color,
                material=material,
                attribute_1=attr1,
                attribute_2=attr2,
                location=location,
                scale_weight=weight_text,
                roll_state=roll_state,
                mapped_roll_weight=mapped_roll_weight,
                mapped_roll_weight_match=mapped_roll_weight_match,
            )

        source = "web_new_roll"
        filament_amount_target = float(app_settings.get("filament_amount_g", 1000.0))

        if roll_state == "used":
            if mapped_roll_weight is None:
                flash(
                    (
                        "No matching roll weight was found in weight_mapping.json for this used-roll profile. "
                        "Try relaxing fallback level or lowering min samples in Settings."
                    ),
                    "error",
                )
                return render_new_roll(
                    step="weight",
                    barcode=barcode,
                    brand=brand,
                    color=color,
                    material=material,
                    attribute_1=attr1,
                    attribute_2=attr2,
                    location=location,
                    scale_weight=weight_text,
                    roll_state=roll_state,
                    mapped_roll_weight=mapped_roll_weight,
                    mapped_roll_weight_match=mapped_roll_weight_match,
                )

            filament_amount_target = round(starting_weight - mapped_roll_weight, 2)
            if filament_amount_target < 0:
                if negative_filament_policy == "block":
                    flash(
                        f"Current weight is below mapped roll weight ({mapped_roll_weight:.2f} g).",
                        "error",
                    )
                    return render_new_roll(
                        step="weight",
                        barcode=barcode,
                        brand=brand,
                        color=color,
                        material=material,
                        attribute_1=attr1,
                        attribute_2=attr2,
                        location=location,
                        scale_weight=weight_text,
                        roll_state=roll_state,
                        mapped_roll_weight=mapped_roll_weight,
                        mapped_roll_weight_match=mapped_roll_weight_match,
                    )

                filament_amount_target = 0.0
                if negative_filament_policy == "warn":
                    flash(
                        (
                            "Current weight is below mapped roll weight "
                            f"({mapped_roll_weight:.2f} g). Continuing with 0.00 g filament."
                        ),
                        "warning",
                    )
            source = "web_new_roll_used"
        elif starting_weight < filament_amount_target:
            flash(
                f"Starting weight must be at least {filament_amount_target:.2f} g based on current settings.",
                "error",
            )
            return render_new_roll(
                step="weight",
                barcode=barcode,
                brand=brand,
                color=color,
                material=material,
                attribute_1=attr1,
                attribute_2=attr2,
                location=location,
                scale_weight=weight_text,
                roll_state=roll_state,
                mapped_roll_weight=mapped_roll_weight,
                mapped_roll_weight_match=mapped_roll_weight_match,
            )

        try:
            created = log_data.add_new_roll_web(
                brand=brand,
                color=color,
                material=material,
                attr1=attr1,
                attr2=attr2,
                location=location,
                starting_weight=starting_weight,
                filament_amount_target=filament_amount_target,
                barcode=barcode,
                source=source,
                empty_threshold=empty_threshold,
            )
        except ValueError as exc:
            flash(str(exc), "error")
            return render_new_roll(
                step="weight",
                barcode=barcode,
                brand=brand,
                color=color,
                material=material,
                attribute_1=attr1,
                attribute_2=attr2,
                location=location,
                scale_weight=weight_text,
                roll_state=roll_state,
                mapped_roll_weight=mapped_roll_weight,
                mapped_roll_weight_match=mapped_roll_weight_match,
            )

        flash(
            (
                f"New filament roll added. Barcode: {created['barcode']} | "
                f"Roll weight: {created['roll_weight']:.2f} g"
            ),
            "success",
        )
        return redirect(url_for("index"))

    return render_new_roll(step="info")


@app.route("/edit_roll/<barcode>", methods=["GET", "POST"])
def edit_roll(barcode):
    target_barcode = str(barcode or "").strip()
    if not target_barcode:
        flash("Barcode is required for editing.", "error")
        return redirect(url_for("index"))

    existing = get_inventory_roll(target_barcode)
    if existing is None:
        flash("Barcode not found.", "error")
        return redirect(url_for("index"))

    options = generate_barcode.get_catalog_options()
    app_settings = settings_store.load_settings()
    _, empty_threshold = get_threshold_settings(app_settings)

    form_data = {
        "brand": existing.get("brand", "") or "",
        "color": existing.get("color", "") or "",
        "material": existing.get("material", "") or "",
        "attribute_1": existing.get("attribute_1", "") or "",
        "attribute_2": existing.get("attribute_2", "") or "",
        "location": existing.get("location", app_settings.get("default_location", "Lab")) or "Lab",
        "filament_amount": f"{float(existing.get('filament_amount', 0.0)):.2f}",
        "roll_weight": (
            ""
            if existing.get("roll_weight") is None
            else f"{float(existing.get('roll_weight', 0.0)):.2f}"
        ),
    }

    if request.method == "POST":
        form_data = {
            "brand": str(request.form.get("brand", "")).strip(),
            "color": str(request.form.get("color", "")).strip(),
            "material": str(request.form.get("material", "")).strip(),
            "attribute_1": str(request.form.get("attribute_1", "")).strip(),
            "attribute_2": str(request.form.get("attribute_2", "")).strip(),
            "location": str(
                request.form.get("location", app_settings.get("default_location", "Lab"))
            ).strip(),
            "filament_amount": str(request.form.get("filament_amount", "")).strip(),
            "roll_weight": str(request.form.get("roll_weight", "")).strip(),
        }

        if not form_data["brand"] or not form_data["color"] or not form_data["material"]:
            flash("Brand, color, and material are required.", "error")
            return render_template(
                "edit_roll.html",
                barcode=target_barcode,
                form_data=form_data,
                brand_options=options["brands"],
                color_options=options["colors"],
                material_options=options["materials"],
                attribute_options=options["attributes"],
                location_options=options["locations"],
                times_logged_out=existing.get("times_logged_out", 0),
            )

        try:
            filament_amount = parse_float(form_data["filament_amount"], "Filament amount")
        except ValueError as exc:
            flash(str(exc), "error")
            return render_template(
                "edit_roll.html",
                barcode=target_barcode,
                form_data=form_data,
                brand_options=options["brands"],
                color_options=options["colors"],
                material_options=options["materials"],
                attribute_options=options["attributes"],
                location_options=options["locations"],
                times_logged_out=existing.get("times_logged_out", 0),
            )

        roll_weight_value = None
        if form_data["roll_weight"]:
            parsed_roll_weight = parse_optional_float(form_data["roll_weight"], default=None)
            if parsed_roll_weight is None:
                flash("Roll weight must be a valid number if provided.", "error")
                return render_template(
                    "edit_roll.html",
                    barcode=target_barcode,
                    form_data=form_data,
                    brand_options=options["brands"],
                    color_options=options["colors"],
                    material_options=options["materials"],
                    attribute_options=options["attributes"],
                    location_options=options["locations"],
                    times_logged_out=existing.get("times_logged_out", 0),
                )
            roll_weight_value = parsed_roll_weight

        if filament_amount < 0:
            flash("Filament amount cannot be negative.", "error")
            return render_template(
                "edit_roll.html",
                barcode=target_barcode,
                form_data=form_data,
                brand_options=options["brands"],
                color_options=options["colors"],
                material_options=options["materials"],
                attribute_options=options["attributes"],
                location_options=options["locations"],
                times_logged_out=existing.get("times_logged_out", 0),
            )

        if roll_weight_value is not None and roll_weight_value < 0:
            flash("Roll weight cannot be negative.", "error")
            return render_template(
                "edit_roll.html",
                barcode=target_barcode,
                form_data=form_data,
                brand_options=options["brands"],
                color_options=options["colors"],
                material_options=options["materials"],
                attribute_options=options["attributes"],
                location_options=options["locations"],
                times_logged_out=existing.get("times_logged_out", 0),
            )

        is_empty = filament_amount <= empty_threshold
        updated = update_inventory_roll(
            barcode=target_barcode,
            brand=form_data["brand"],
            color=form_data["color"],
            material=form_data["material"],
            attribute_1=form_data["attribute_1"],
            attribute_2=form_data["attribute_2"],
            location=form_data["location"],
            filament_amount=round(filament_amount, 2),
            roll_weight=round(roll_weight_value, 2) if roll_weight_value is not None else None,
            is_empty=is_empty,
        )
        if not updated:
            flash("Failed to update roll data.", "error")
            return render_template(
                "edit_roll.html",
                barcode=target_barcode,
                form_data=form_data,
                brand_options=options["brands"],
                color_options=options["colors"],
                material_options=options["materials"],
                attribute_options=options["attributes"],
                location_options=options["locations"],
                times_logged_out=existing.get("times_logged_out", 0),
            )

        flash(f"Roll {target_barcode} updated successfully.", "success")
        return redirect(url_for("index"))

    return render_template(
        "edit_roll.html",
        barcode=target_barcode,
        form_data=form_data,
        brand_options=options["brands"],
        color_options=options["colors"],
        material_options=options["materials"],
        attribute_options=options["attributes"],
        location_options=options["locations"],
        times_logged_out=existing.get("times_logged_out", 0),
    )


@app.route("/toggle_favorite", methods=["POST"])
def toggle_favorite():
    payload = request.get_json(silent=True) or {}
    barcode = str(payload.get("barcode", "")).strip()
    if not barcode:
        return jsonify({"error": "Missing barcode"}), 400

    is_favorite = toggle_inventory_favorite(barcode)
    if is_favorite is None:
        return jsonify({"error": "Barcode not found"}), 404

    return jsonify({"is_favorite": bool(is_favorite)}), 200


@app.route("/favorites")
def favorites():
    rows = get_inventory_rows()
    app_settings = settings_store.load_settings()
    low_threshold, _ = get_threshold_settings(app_settings)
    color_search_tokens = color_search.get_color_search_tokens_by_color()

    def key_norm(value):
        return str(value).strip().lower() if value is not None else ""

    def display_norm(value):
        return str(value).strip() if value is not None else ""

    def parse_number(value):
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            text = str(value).strip().replace(",", "")
            if not text:
                return None
            try:
                return float(text)
            except ValueError:
                return None

    counts = {}
    for row in rows:
        key = (
            key_norm(row[2] if len(row) > 2 else ""),
            key_norm(row[3] if len(row) > 3 else ""),
            key_norm(row[4] if len(row) > 4 else ""),
            key_norm(row[5] if len(row) > 5 else ""),
            key_norm(row[6] if len(row) > 6 else ""),
        )
        entry = counts.setdefault(key, {"total": 0, "low": 0})
        entry["total"] += 1

        amount = parse_number(row[7] if len(row) > 7 else None)
        if amount is not None and amount < low_threshold:
            entry["low"] += 1

    unique_favorites = {}
    for row in rows:
        is_favorite = len(row) > 12 and str(row[12]).strip().lower() == "true"
        if not is_favorite:
            continue

        brand = display_norm(row[2] if len(row) > 2 else "")
        color = display_norm(row[3] if len(row) > 3 else "")
        material = display_norm(row[4] if len(row) > 4 else "")
        attr1 = display_norm(row[5] if len(row) > 5 else "")
        attr2 = display_norm(row[6] if len(row) > 6 else "")

        group_key = (brand.lower(), color.lower(), material.lower(), attr1.lower(), attr2.lower())
        if group_key in unique_favorites:
            continue

        order_link = order_links.build_order_link(
            brand=brand,
            color=color,
            material=material,
            attribute_1=attr1,
            attribute_2=attr2,
        )

        group_counts = counts.get(group_key, {"total": 0, "low": 0})

        unique_favorites[group_key] = {
            "brand": brand,
            "color": color,
            "material": material,
            "attribute_1": attr1,
            "attribute_2": attr2,
            "order_url": order_link.get("url", ""),
            "order_label": order_link.get("label", "Order"),
            "total_count": group_counts["total"],
            "low_count": group_counts["low"],
        }

    return render_template(
        "favorites.html",
        favorites=list(unique_favorites.values()),
        color_search_tokens=color_search_tokens,
    )


@app.route("/settings", methods=["GET", "POST"])
def settings():
    current = settings_store.load_settings()

    if request.method == "POST":
        updates = {
            "theme": request.form.get("theme", current.get("theme", "light")),
            "alert_mode": request.form.get("alert_mode", current.get("alert_mode", "all")),
            "rows_per_page": request.form.get("rows_per_page", current.get("rows_per_page", 20)),
            "default_location": request.form.get(
                "default_location", current.get("default_location", "Lab")
            ),
            "popular_weeks": request.form.get("popular_weeks", current.get("popular_weeks", 4)),
            "filament_amount_g": request.form.get(
                "filament_amount_g", current.get("filament_amount_g", 1000.0)
            ),
            "low_threshold_g": request.form.get(
                "low_threshold_g", current.get("low_threshold_g", LOW_THRESHOLD)
            ),
            "empty_threshold_g": request.form.get(
                "empty_threshold_g", current.get("empty_threshold_g", EMPTY_THRESHOLD)
            ),
            "default_roll_condition": request.form.get(
                "default_roll_condition", current.get("default_roll_condition", "new")
            ),
            "used_roll_map_fallback_level": request.form.get(
                "used_roll_map_fallback_level",
                current.get("used_roll_map_fallback_level", "material"),
            ),
            "used_roll_map_min_samples": request.form.get(
                "used_roll_map_min_samples", current.get("used_roll_map_min_samples", 1)
            ),
            "scale_timeout_sec": request.form.get(
                "scale_timeout_sec", current.get("scale_timeout_sec", 5)
            ),
            "scale_retry_count": request.form.get(
                "scale_retry_count", current.get("scale_retry_count", 2)
            ),
            "negative_filament_policy": request.form.get(
                "negative_filament_policy", current.get("negative_filament_policy", "block")
            ),
            "backup_retention_days": request.form.get(
                "backup_retention_days", current.get("backup_retention_days", 30)
            ),
            "low_stock_alerts": request.form.get("low_stock_alerts") == "on",
            "auto_read_scale_on_weight_step": request.form.get("auto_read_scale_on_weight_step")
            == "on",
            "auto_backup_on_write": request.form.get("auto_backup_on_write") == "on",
        }
        settings_store.save_settings(updates)
        flash("Settings saved.", "success")
        return redirect(url_for("settings"))

    return render_template(
        "settings.html",
        settings=current,
        theme_options=settings_store.THEME_OPTIONS,
        alert_mode_options=settings_store.ALERT_MODE_OPTIONS,
        roll_condition_options=settings_store.ROLL_CONDITION_OPTIONS,
        used_roll_map_level_options=settings_store.USED_ROLL_MAP_LEVEL_OPTIONS,
        negative_filament_policy_options=settings_store.NEGATIVE_FILAMENT_POLICY_OPTIONS,
    )


if __name__ == "__main__":
    debug_mode = os.getenv("FLASK_DEBUG", "1") == "1"
    app.run(debug=debug_mode)
