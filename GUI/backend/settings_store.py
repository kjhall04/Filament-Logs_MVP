import json
import os
from copy import deepcopy

from backend.config import SETTINGS_PATH

THEME_OPTIONS = ("light", "dark")
ALERT_MODE_OPTIONS = ("all", "errors_only", "silent", "browser")
ROLL_CONDITION_OPTIONS = ("new", "used")
USED_ROLL_MAP_LEVEL_OPTIONS = (
    "brand+color+material+attributes",
    "brand+material+attributes",
    "brand+material",
    "material+attributes",
    "material",
)
NEGATIVE_FILAMENT_POLICY_OPTIONS = ("block", "warn", "clamp_to_zero")

DEFAULT_SETTINGS = {
    "theme": "light",
    "alert_mode": "all",
    "rows_per_page": 20,
    "default_location": "Lab",
    "popular_weeks": 4,
    "filament_amount_g": 1000.0,
    "low_threshold_g": 250.0,
    "empty_threshold_g": 5.0,
    "default_roll_condition": "new",
    "used_roll_map_fallback_level": "material",
    "used_roll_map_min_samples": 1,
    "scale_timeout_sec": 5,
    "scale_retry_count": 2,
    "auto_read_scale_on_weight_step": False,
    "negative_filament_policy": "block",
    "auto_backup_on_write": False,
    "backup_retention_days": 30,
    "low_stock_alerts": True,
}


def _ensure_parent_dir():
    parent = os.path.dirname(SETTINGS_PATH) or "."
    os.makedirs(parent, exist_ok=True)


def _to_int(value, default, min_value, max_value):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(min_value, min(max_value, parsed))


def _to_float(value, default, min_value, max_value):
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return max(min_value, min(max_value, parsed))


def _to_bool(value, default=False):
    if value is None:
        return default
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on")
    return bool(value)


def sanitize_settings(raw):
    settings = deepcopy(DEFAULT_SETTINGS)
    if isinstance(raw, dict):
        settings.update(raw)

    theme = str(settings.get("theme", DEFAULT_SETTINGS["theme"])).strip().lower()
    settings["theme"] = theme if theme in THEME_OPTIONS else DEFAULT_SETTINGS["theme"]

    alert_mode = str(settings.get("alert_mode", DEFAULT_SETTINGS["alert_mode"])).strip().lower()
    settings["alert_mode"] = (
        alert_mode if alert_mode in ALERT_MODE_OPTIONS else DEFAULT_SETTINGS["alert_mode"]
    )

    settings["rows_per_page"] = _to_int(settings.get("rows_per_page"), 20, 5, 200)
    settings["popular_weeks"] = _to_int(settings.get("popular_weeks"), 4, 0, 104)
    settings["filament_amount_g"] = _to_float(settings.get("filament_amount_g"), 1000.0, 100.0, 10000.0)
    settings["low_threshold_g"] = _to_float(settings.get("low_threshold_g"), 250.0, 0.0, 10000.0)
    settings["empty_threshold_g"] = _to_float(settings.get("empty_threshold_g"), 5.0, 0.0, 1000.0)

    default_location = str(settings.get("default_location", "Lab")).strip()
    settings["default_location"] = default_location if default_location in ("Lab", "Storage") else "Lab"

    default_roll_condition = str(
        settings.get("default_roll_condition", DEFAULT_SETTINGS["default_roll_condition"])
    ).strip().lower()
    settings["default_roll_condition"] = (
        default_roll_condition
        if default_roll_condition in ROLL_CONDITION_OPTIONS
        else DEFAULT_SETTINGS["default_roll_condition"]
    )

    used_roll_map_fallback_level = str(
        settings.get(
            "used_roll_map_fallback_level", DEFAULT_SETTINGS["used_roll_map_fallback_level"]
        )
    ).strip().lower()
    settings["used_roll_map_fallback_level"] = (
        used_roll_map_fallback_level
        if used_roll_map_fallback_level in USED_ROLL_MAP_LEVEL_OPTIONS
        else DEFAULT_SETTINGS["used_roll_map_fallback_level"]
    )

    settings["used_roll_map_min_samples"] = _to_int(
        settings.get("used_roll_map_min_samples"),
        DEFAULT_SETTINGS["used_roll_map_min_samples"],
        1,
        1000,
    )

    settings["scale_timeout_sec"] = _to_int(
        settings.get("scale_timeout_sec"),
        DEFAULT_SETTINGS["scale_timeout_sec"],
        1,
        60,
    )
    settings["scale_retry_count"] = _to_int(
        settings.get("scale_retry_count"),
        DEFAULT_SETTINGS["scale_retry_count"],
        1,
        10,
    )

    settings["auto_read_scale_on_weight_step"] = _to_bool(
        settings.get("auto_read_scale_on_weight_step"),
        DEFAULT_SETTINGS["auto_read_scale_on_weight_step"],
    )

    negative_filament_policy = str(
        settings.get("negative_filament_policy", DEFAULT_SETTINGS["negative_filament_policy"])
    ).strip().lower()
    settings["negative_filament_policy"] = (
        negative_filament_policy
        if negative_filament_policy in NEGATIVE_FILAMENT_POLICY_OPTIONS
        else DEFAULT_SETTINGS["negative_filament_policy"]
    )

    settings["auto_backup_on_write"] = _to_bool(
        settings.get("auto_backup_on_write"), DEFAULT_SETTINGS["auto_backup_on_write"]
    )
    settings["backup_retention_days"] = _to_int(
        settings.get("backup_retention_days"),
        DEFAULT_SETTINGS["backup_retention_days"],
        1,
        3650,
    )

    settings["low_stock_alerts"] = _to_bool(
        settings.get("low_stock_alerts", DEFAULT_SETTINGS["low_stock_alerts"]),
        DEFAULT_SETTINGS["low_stock_alerts"],
    )

    return settings


def load_settings():
    _ensure_parent_dir()
    if not os.path.exists(SETTINGS_PATH):
        return deepcopy(DEFAULT_SETTINGS)

    try:
        with open(SETTINGS_PATH, "r", encoding="utf-8") as file:
            data = json.load(file)
    except Exception:
        return deepcopy(DEFAULT_SETTINGS)

    return sanitize_settings(data)


def save_settings(updates):
    current = load_settings()
    if isinstance(updates, dict):
        current.update(updates)
    sanitized = sanitize_settings(current)

    _ensure_parent_dir()
    with open(SETTINGS_PATH, "w", encoding="utf-8") as file:
        json.dump(sanitized, file, indent=2)

    return sanitized
