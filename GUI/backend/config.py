import os

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")

DEFAULT_EXCEL_PATH = os.path.join(DATA_DIR, "filament_inventory.xlsx")
DEFAULT_DATABASE_PATH = os.path.join(DATA_DIR, "filament_inventory.db")
DEFAULT_SETTINGS_PATH = os.path.join(DATA_DIR, "settings.json")

EXCEL_PATH = os.getenv("EXCEL_PATH", DEFAULT_EXCEL_PATH)
DATABASE_PATH = os.getenv("DATABASE_PATH", DEFAULT_DATABASE_PATH)
SETTINGS_PATH = os.getenv("SETTINGS_PATH", DEFAULT_SETTINGS_PATH)

EMPTY_THRESHOLD = float(os.getenv("EMPTY_THRESHOLD", "5"))
LOW_THRESHOLD = float(os.getenv("LOW_THRESHOLD", "250"))
