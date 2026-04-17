import os
import re

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
STATIC_DATA_DIR = os.path.join(BASE_DIR, "data")
DATA_DIR = STATIC_DATA_DIR


def _sanitize_path_fragment(value, fallback="default"):
    text = re.sub(r"[^A-Za-z0-9._-]+", "-", str(value or "").strip())
    text = text.strip(".-")
    return text or fallback


def _default_writable_data_dir():
    configured = str(os.getenv("FILAMENT_LOGS_WRITABLE_DIR", "")).strip()
    if configured:
        return configured

    if os.getenv("VERCEL") == "1" or os.getenv("VERCEL_ENV"):
        temp_root = (
            str(os.getenv("TMPDIR", "")).strip()
            or str(os.getenv("TEMP", "")).strip()
            or "/tmp"
        )
        instance_key = (
            str(os.getenv("FILAMENT_LOGS_INSTANCE_KEY", "")).strip()
            or str(os.getenv("VERCEL_GIT_COMMIT_SHA", "")).strip()
            or str(os.getenv("VERCEL_URL", "")).strip()
            or "default"
        )
        return os.path.join(
            temp_root,
            "filament-logs",
            _sanitize_path_fragment(instance_key),
        )

    return STATIC_DATA_DIR


WRITABLE_DATA_DIR = _default_writable_data_dir()

DEFAULT_EXCEL_PATH = os.path.join(STATIC_DATA_DIR, "filament_inventory.xlsx")
DEFAULT_DATABASE_PATH = os.path.join(WRITABLE_DATA_DIR, "filament_inventory.db")
DEFAULT_SETTINGS_PATH = os.path.join(WRITABLE_DATA_DIR, "settings.json")

EXCEL_PATH = os.getenv("EXCEL_PATH", DEFAULT_EXCEL_PATH)
DATABASE_PATH = os.getenv("DATABASE_PATH", DEFAULT_DATABASE_PATH)
SETTINGS_PATH = os.getenv("SETTINGS_PATH", DEFAULT_SETTINGS_PATH)

EMPTY_THRESHOLD = float(os.getenv("EMPTY_THRESHOLD", "5"))
LOW_THRESHOLD = float(os.getenv("LOW_THRESHOLD", "250"))
