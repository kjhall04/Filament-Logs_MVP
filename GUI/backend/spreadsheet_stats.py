from datetime import datetime, timedelta

from backend.config import EMPTY_THRESHOLD, LOW_THRESHOLD
from backend.workbook_store import list_inventory_rows, open_database


def _parse_timestamp(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).strip()
    if not text:
        return None

    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue

    return None


def _to_float(value, default=None):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _to_int(value, default=0):
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _inventory_records():
    records = []
    for row in list_inventory_rows():
        barcode = ""
        if row and len(row) > 1 and row[1] is not None:
            barcode = str(row[1]).strip()

        last_logged = row[0] if len(row) > 0 else None
        records.append(
            {
                "last_logged": last_logged,
                "last_logged_dt": _parse_timestamp(last_logged),
                "barcode": barcode,
                "brand": row[2] if len(row) > 2 else None,
                "color": row[3] if len(row) > 3 else None,
                "material": row[4] if len(row) > 4 else None,
                "attribute_1": row[5] if len(row) > 5 else None,
                "attribute_2": row[6] if len(row) > 6 else None,
                "weight": _to_float(row[7], default=0.0) if len(row) > 7 else 0.0,
                "location": row[8] if len(row) > 8 else None,
                "roll_weight": _to_float(row[9]) if len(row) > 9 else None,
                "times_logged_out": _to_int(row[10], default=0) if len(row) > 10 else 0,
                "is_empty": str(row[11]).strip().lower() == "true" if len(row) > 11 else False,
                "is_favorite": str(row[12]).strip().lower() == "true" if len(row) > 12 else False,
            }
        )

    return records


def _usage_counts_since(cutoff):
    counts = {}
    with open_database(write=False) as conn:
        rows = conn.execute(
            """
            SELECT timestamp, barcode
            FROM usage_events
            WHERE LOWER(COALESCE(event_type, '')) = 'log_usage'
              AND barcode IS NOT NULL
              AND TRIM(barcode) != ''
            """
        ).fetchall()

    for row in rows:
        event_timestamp = _parse_timestamp(row["timestamp"])
        barcode = str(row["barcode"]).strip() if row["barcode"] is not None else ""
        if not barcode or event_timestamp is None or event_timestamp < cutoff:
            continue
        counts[barcode] = counts.get(barcode, 0) + 1

    return counts


def get_most_popular_filaments(top_n: int = 10, weeks: int | None = None):
    records = _inventory_records()

    if weeks is not None:
        cutoff = datetime.now() - timedelta(weeks=weeks)
        usage_counts = _usage_counts_since(cutoff)

        if usage_counts:
            filtered = []
            for record in records:
                count = usage_counts.get(record["barcode"], 0)
                if count <= 0:
                    continue
                updated = dict(record)
                updated["times_logged_out"] = count
                filtered.append(updated)
            records = filtered
        else:
            records = [
                record
                for record in records
                if record["last_logged_dt"] is not None and record["last_logged_dt"] >= cutoff
            ]

    records.sort(key=lambda item: item.get("times_logged_out", 0), reverse=True)

    return [
        {
            "brand": item.get("brand"),
            "color": item.get("color"),
            "material": item.get("material"),
            "attribute_1": item.get("attribute_1"),
            "attribute_2": item.get("attribute_2"),
            "times_logged_out": item.get("times_logged_out", 0),
            "weight": item.get("weight"),
            "is_favorite": "true" if item.get("is_favorite") else "false",
        }
        for item in records[:top_n]
    ]


def get_low_or_empty_filaments(
    low_threshold: float = LOW_THRESHOLD, empty_threshold: float = EMPTY_THRESHOLD
):
    records = _inventory_records()
    results = []

    for record in records:
        is_empty = record["is_empty"] or record["weight"] <= empty_threshold
        if is_empty or record["weight"] < low_threshold:
            results.append(
                {
                    "brand": record["brand"],
                    "color": record["color"],
                    "material": record["material"],
                    "attribute_1": record["attribute_1"],
                    "attribute_2": record["attribute_2"],
                    "weight": record["weight"],
                    "is_favorite": "true" if record["is_favorite"] else "false",
                }
            )

    return results


def get_empty_rolls(empty_threshold: float = EMPTY_THRESHOLD):
    records = _inventory_records()
    empty_records = [
        record for record in records if record["is_empty"] or record["weight"] <= empty_threshold
    ]
    empty_records.sort(
        key=lambda item: item["last_logged_dt"] if item["last_logged_dt"] is not None else datetime.min,
        reverse=True,
    )

    return [
        {
            "brand": item["brand"],
            "color": item["color"],
            "material": item["material"],
            "attribute_1": item["attribute_1"],
            "attribute_2": item["attribute_2"],
            "times_logged_out": item["times_logged_out"],
            "last_logged": item["last_logged"],
            "is_favorite": "true" if item["is_favorite"] else "false",
        }
        for item in empty_records
    ]
