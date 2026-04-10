import json
import os

from backend.config import DATA_DIR

COLOR_MAPPING_PATH = os.path.join(DATA_DIR, "color_mapping.json")

CATEGORY_ALIASES = {
    "gray": ("grey",),
    "dual color": ("multicolor", "multi color", "two color"),
    "triple color": ("multicolor", "multi color", "three color", "tri color"),
    "gradient colors": ("gradient", "rainbow", "chameleon"),
    "transparent": ("clear", "translucent"),
    "metallic": ("metal", "shimmer"),
    "fluorescent": ("neon",),
}


def _normalize(value):
    return " ".join(str(value or "").split()).strip().lower()


def _load_color_mapping():
    try:
        with open(COLOR_MAPPING_PATH, "r", encoding="utf-8") as handle:
            data = json.load(handle)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _category_tokens(category_name):
    normalized_category = _normalize(category_name)
    if not normalized_category:
        return set()

    tokens = {normalized_category, normalized_category.replace(" ", "")}
    for alias in CATEGORY_ALIASES.get(normalized_category, ()):
        normalized_alias = _normalize(alias)
        if normalized_alias:
            tokens.add(normalized_alias)
    return tokens


def get_color_search_tokens_by_color():
    mapping = _load_color_mapping()
    result = {}
    for category_name, entries in mapping.items():
        if not isinstance(entries, dict):
            continue

        tokens = _category_tokens(category_name)
        if not tokens:
            continue

        for _, color_value in entries.items():
            color_key = _normalize(color_value)
            if not color_key:
                continue
            bucket = result.setdefault(color_key, set())
            bucket.update(tokens)

    return {
        color_name: sorted(tokens)
        for color_name, tokens in result.items()
        if tokens
    }
