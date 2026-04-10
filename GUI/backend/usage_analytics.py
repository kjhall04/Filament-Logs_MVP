from datetime import datetime

from backend.workbook_store import normalize_text_case, open_database


def _to_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _normalize_label(value, fallback="Unknown", field=None):
    text = normalize_text_case(value, field=field)
    return text if text else fallback


def _sort_buckets(items, key_name):
    rows = []
    for label, stats in items.items():
        rows.append(
            {
                key_name: label,
                "used_g": round(stats["used_g"], 2),
                "event_count": int(stats["event_count"]),
            }
        )

    rows.sort(key=lambda row: (-row["used_g"], row[key_name]))
    return rows


def get_usage_summary(start_ts=None, end_ts=None):
    query = [
        """
        SELECT
            timestamp,
            barcode,
            brand,
            color,
            material,
            delta_used
        FROM usage_events
        WHERE LOWER(COALESCE(event_type, '')) = 'log_usage'
          AND COALESCE(delta_used, 0) > 0
        """
    ]
    params = []

    if start_ts:
        query.append("AND timestamp >= ?")
        params.append(str(start_ts))
    if end_ts:
        query.append("AND timestamp <= ?")
        params.append(str(end_ts))

    query.append("ORDER BY timestamp ASC")
    sql = "\n".join(query)

    with open_database(write=False) as conn:
        rows = conn.execute(sql, tuple(params)).fetchall()

    total_used = 0.0
    event_count = 0
    rolls_touched = set()
    by_material = {}
    by_color = {}
    by_day = {}
    first_event = ""
    last_event = ""

    for row in rows:
        used_g = _to_float(row["delta_used"], 0.0)
        if used_g <= 0:
            continue

        timestamp = str(row["timestamp"] or "").strip()
        if timestamp:
            if not first_event:
                first_event = timestamp
            last_event = timestamp

        total_used += used_g
        event_count += 1

        barcode = str(row["barcode"] or "").strip()
        if barcode:
            rolls_touched.add(barcode)

        material = _normalize_label(row["material"], field="material")
        color = _normalize_label(row["color"], field="color")

        material_bucket = by_material.setdefault(material, {"used_g": 0.0, "event_count": 0})
        material_bucket["used_g"] += used_g
        material_bucket["event_count"] += 1

        color_bucket = by_color.setdefault(color, {"used_g": 0.0, "event_count": 0})
        color_bucket["used_g"] += used_g
        color_bucket["event_count"] += 1

        day_key = ""
        if timestamp:
            try:
                day_key = datetime.strptime(timestamp[:19], "%Y-%m-%d %H:%M:%S").strftime("%Y-%m-%d")
            except ValueError:
                day_key = timestamp[:10]
        if day_key:
            by_day[day_key] = by_day.get(day_key, 0.0) + used_g

    daily_usage = [
        {"date": day, "used_g": round(amount, 2)}
        for day, amount in sorted(by_day.items(), key=lambda item: item[0])
    ]

    return {
        "total_used_g": round(total_used, 2),
        "event_count": event_count,
        "rolls_touched": len(rolls_touched),
        "average_per_event_g": round(total_used / event_count, 2) if event_count else 0.0,
        "first_event": first_event,
        "last_event": last_event,
        "by_material": _sort_buckets(by_material, "material"),
        "by_color": _sort_buckets(by_color, "color"),
        "daily_usage": daily_usage,
    }
