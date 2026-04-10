import json
import os
from urllib.parse import quote_plus

from backend.config import DATA_DIR

DEFAULT_ORDER_LINKS_PATH = os.path.join(DATA_DIR, "order_links.json")
DEFAULT_ORDER_LINKS = {
    "default": {
        "label": "Amazon",
        "url_template": "https://www.amazon.com/s?k={query}",
    },
    "brands": {
        "bambu labs": {
            "label": "Bambu Store",
            "url_template": "https://us.store.bambulab.com/search?q={query}",
        },
        "prusa": {
            "label": "Prusa Store",
            "url_template": "https://www.prusa3d.com/search/?q={query}",
        },
        "polymaker": {
            "label": "Polymaker",
            "url_template": "https://us.polymaker.com/search?q={query}",
        },
        "matterhackers": {
            "label": "MatterHackers",
            "url_template": "https://www.matterhackers.com/store/search?query={query}",
        },
    },
}


def _normalize_text(value):
    return " ".join(str(value or "").split()).strip()


def _normalize_brand_key(value):
    return _normalize_text(value).lower()


def _sanitize_entry(entry, fallback):
    if not isinstance(entry, dict):
        return dict(fallback)

    label = _normalize_text(entry.get("label", fallback.get("label", "Order")))
    template = _normalize_text(entry.get("url_template", fallback.get("url_template", "")))

    if not label:
        label = fallback.get("label", "Order")
    if not template:
        template = fallback.get("url_template", "")

    return {"label": label, "url_template": template}


def get_order_links_path():
    configured = _normalize_text(os.getenv("ORDER_LINKS_PATH"))
    return configured or DEFAULT_ORDER_LINKS_PATH


def load_order_links_config():
    path = get_order_links_path()
    raw = {}
    try:
        with open(path, "r", encoding="utf-8") as handle:
            raw = json.load(handle)
    except Exception:
        raw = {}

    default_entry = _sanitize_entry(raw.get("default"), DEFAULT_ORDER_LINKS["default"])
    raw_brands = raw.get("brands", {})
    if not isinstance(raw_brands, dict):
        raw_brands = {}

    normalized_brands = {}
    for brand, entry in raw_brands.items():
        key = _normalize_brand_key(brand)
        if not key:
            continue
        normalized_brands[key] = _sanitize_entry(entry, default_entry)

    config = {
        "default": default_entry,
        "brands": normalized_brands,
        "path": path,
    }
    return config


def _is_safe_template(template):
    return template.startswith("https://") or template.startswith("http://")


def build_order_link(brand, color="", material="", attribute_1="", attribute_2=""):
    brand_clean = _normalize_text(brand)
    color_clean = _normalize_text(color)
    material_clean = _normalize_text(material)
    attr1_clean = _normalize_text(attribute_1)
    attr2_clean = _normalize_text(attribute_2)

    config = load_order_links_config()
    selected = config["brands"].get(_normalize_brand_key(brand_clean), config["default"])
    template = selected.get("url_template", "")
    if not template or not _is_safe_template(template):
        return {"label": "", "url": ""}

    query_parts = [brand_clean, color_clean, material_clean, attr1_clean, attr2_clean, "filament"]
    query_text = " ".join([part for part in query_parts if part]).strip()

    substitutions = {
        "query": quote_plus(query_text),
        "brand": quote_plus(brand_clean),
        "color": quote_plus(color_clean),
        "material": quote_plus(material_clean),
        "attribute_1": quote_plus(attr1_clean),
        "attribute_2": quote_plus(attr2_clean),
    }

    try:
        rendered_url = template.format(**substitutions)
    except Exception:
        return {"label": "", "url": ""}

    if not _is_safe_template(rendered_url):
        return {"label": "", "url": ""}

    label = _normalize_text(selected.get("label", "Order")) or "Order"
    return {"label": label, "url": rendered_url}
