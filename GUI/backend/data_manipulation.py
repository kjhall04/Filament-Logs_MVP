import json
import os
import struct
import time

from backend.workbook_store import get_roll_weight as get_roll_weight_db

try:
    import hid
except Exception:
    hid = None

VENDOR_ID = 0x0922
PRODUCT_ID = 0x8003
FILAMENT_AMOUNT = 1000.0

BASE_DIR = os.path.dirname(__file__)
WEIGHT_MAPPING_PATH = os.path.join(BASE_DIR, "..", "data", "weight_mapping.json")
WEIGHT_MAP_LEVEL_ORDER = (
    "brand+color+material+attributes",
    "brand+material+attributes",
    "brand+material",
    "material+attributes",
    "material",
)


def _read_scale_weight_once(timeout_sec: int):
    """
    Read a single weight (grams) from the scale once.
    Returns float grams or None on timeout/error.
    """
    if hid is None:
        return None

    device = None
    try:
        device = hid.device()
        device.open(VENDOR_ID, PRODUCT_ID)
        device.set_nonblocking(False)

        deadline = time.time() + timeout_sec
        while time.time() < deadline:
            data = device.read(6)
            if not data:
                time.sleep(0.1)
                continue

            try:
                weight_raw = struct.unpack("<h", bytes(data[4:6]))[0]
            except Exception:
                return None

            units = "g" if len(data) > 2 and data[2] == 2 else "oz"
            if units == "oz":
                return round(weight_raw * 28.3495, 2)
            return float(weight_raw)

        return None
    except Exception:
        return None
    finally:
        try:
            if device is not None:
                device.close()
        except Exception:
            pass


def read_scale_weight(timeout_sec: int = 5, retry_count: int = 1):
    attempts = max(int(retry_count or 1), 1)
    timeout_value = max(int(timeout_sec or 1), 1)

    for _ in range(attempts):
        reading = _read_scale_weight_once(timeout_sec=timeout_value)
        if reading is not None:
            return reading
    return None


def get_starting_weight(timeout_sec: int = 5):
    """
    Compatibility wrapper used by web flow.
    Returns (weight, "g") where weight can be None.
    """
    return read_scale_weight(timeout_sec=timeout_sec), "g"


def get_roll_weight(barcode: str, sheet):
    """
    Return roll weight (float) for barcode from the SQLite store.
    Returns None when no numeric value can be found.
    """
    _ = sheet  # Retained for backwards compatibility with old callers.
    return get_roll_weight_db(barcode)


def _normalize_text(value):
    return str(value or "").strip().casefold()


def _to_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_int(value, default=0):
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _build_weight_key(*parts):
    return "|".join(_normalize_text(part) for part in parts)


def _load_weight_mapping_levels():
    mapping = _load_json(WEIGHT_MAPPING_PATH)
    if not isinstance(mapping, dict):
        return {}
    levels = mapping.get("levels")
    return levels if isinstance(levels, dict) else {}


def _parse_weight_mapping_entry(entry):
    if isinstance(entry, dict):
        weight = _to_float(entry.get("weight"))
        samples = max(_to_int(entry.get("samples"), default=1), 1)
        return weight, samples

    return _to_float(entry), 1


def get_roll_weight_from_map(
    sheet,
    brand: str,
    color: str,
    material: str,
    attribute_1: str,
    attribute_2: str,
    max_fallback_level: str = "material",
    min_samples: int = 1,
):
    """
    Estimate roll weight for a used roll using weight_mapping.json.
    Returns (weight, match_level) where weight is rounded to 2 decimals.
    """
    _ = sheet  # Kept for compatibility with existing callers.

    target_brand = _normalize_text(brand)
    target_color = _normalize_text(color)
    target_material = _normalize_text(material)
    target_attr1 = _normalize_text(attribute_1)
    target_attr2 = _normalize_text(attribute_2)

    if not target_material:
        return None, None

    levels = _load_weight_mapping_levels()
    if not levels:
        return None, None

    queries = (
        (
            "brand+color+material+attributes",
            _build_weight_key(target_brand, target_color, target_material, target_attr1, target_attr2),
        ),
        (
            "brand+material+attributes",
            _build_weight_key(target_brand, target_material, target_attr1, target_attr2),
        ),
        ("brand+material", _build_weight_key(target_brand, target_material)),
        ("material+attributes", _build_weight_key(target_material, target_attr1, target_attr2)),
        ("material", _build_weight_key(target_material)),
    )

    fallback = _normalize_text(max_fallback_level)
    if fallback not in WEIGHT_MAP_LEVEL_ORDER:
        fallback = "material"
    max_index = WEIGHT_MAP_LEVEL_ORDER.index(fallback)
    required_samples = max(_to_int(min_samples, default=1), 1)

    for idx, (level_name, level_key) in enumerate(queries):
        if idx > max_index:
            break
        level_map = levels.get(level_name)
        if not isinstance(level_map, dict):
            continue
        mapped_weight, mapped_samples = _parse_weight_mapping_entry(level_map.get(level_key))
        if mapped_weight is None or mapped_weight <= 0:
            continue
        if mapped_samples < required_samples:
            continue
        return round(float(mapped_weight), 2), level_name

    return None, None


def decode_barcode(barcode: str):
    """
    Decode a 17-digit barcode into
    (brand, color, material, attr1, attr2, location).
    """
    if len(barcode) != 17 or not barcode.isdigit():
        raise ValueError("Barcode must be exactly 17 digits long.")

    brand_mapping = _load_json(os.path.join(BASE_DIR, "..", "data", "brand_mapping.json"))
    color_mapping = _load_json(os.path.join(BASE_DIR, "..", "data", "color_mapping.json"))
    material_mapping = _load_json(os.path.join(BASE_DIR, "..", "data", "material_mapping.json"))
    attribute_mapping = _load_json(os.path.join(BASE_DIR, "..", "data", "attribute_mapping.json"))

    flat_color_mapping = {}
    for _, value in color_mapping.items():
        if isinstance(value, dict):
            flat_color_mapping.update(value)

    brand_code = barcode[:2]
    color_code = barcode[2:5]
    material_code = barcode[5:7]
    attr1_code = barcode[7:9]
    attr2_code = barcode[9:11]
    location_code = barcode[11]

    brand = brand_mapping.get(brand_code, "Unknown Brand")
    color = flat_color_mapping.get(color_code, "Unknown Color")
    material = material_mapping.get(material_code, "Unknown Material")
    attr1 = attribute_mapping.get(attr1_code, "Unknown Attribute")
    attr2 = attribute_mapping.get(attr2_code, "Unknown Attribute")
    location = "Lab" if location_code == "0" else "Storage"

    return brand, color, material, attr1, attr2, location


def _load_json(filepath):
    try:
        with open(filepath, "r", encoding="utf-8") as file:
            return json.load(file)
    except Exception:
        return {}
