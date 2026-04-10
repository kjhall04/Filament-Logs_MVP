from datetime import datetime

from backend import generate_barcode
from backend.config import EMPTY_THRESHOLD
from backend.workbook_store import normalize_text_case, open_database


def _timestamp_now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


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


def _append_event(
    conn,
    timestamp,
    event_type,
    barcode,
    brand,
    color,
    material,
    attr1,
    attr2,
    location,
    input_weight,
    roll_weight,
    filament_amount,
    delta_used,
    times_logged_out,
    source,
):
    brand = normalize_text_case(brand, field="brand")
    color = normalize_text_case(color, field="color")
    material = normalize_text_case(material, field="material")
    attr1 = normalize_text_case(attr1, field="attribute_1")
    attr2 = normalize_text_case(attr2, field="attribute_2")
    location = normalize_text_case(location, field="location")

    conn.execute(
        """
        INSERT INTO usage_events (
            timestamp,
            event_type,
            barcode,
            brand,
            color,
            material,
            attribute_1,
            attribute_2,
            location,
            input_weight,
            roll_weight,
            filament_amount,
            delta_used,
            times_logged_out,
            source
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            timestamp,
            event_type,
            barcode,
            brand,
            color,
            material,
            attr1,
            attr2,
            location,
            input_weight,
            roll_weight,
            filament_amount,
            delta_used,
            times_logged_out,
            source,
        ),
    )


def log_filament_data_web(
    barcode,
    filament_amount,
    roll_weight=None,
    total_weight=None,
    source="web",
    empty_threshold=EMPTY_THRESHOLD,
):
    """
    Update an existing roll identified by barcode and append a usage event.
    Returns True when the barcode exists, otherwise False.
    """
    timestamp = _timestamp_now()
    target_barcode = str(barcode).strip()
    threshold_value = _to_float(empty_threshold, default=EMPTY_THRESHOLD)

    with open_database(write=True) as conn:
        row = conn.execute(
            """
            SELECT
                barcode,
                brand,
                color,
                material,
                attribute_1,
                attribute_2,
                location,
                filament_amount,
                roll_weight,
                times_logged_out
            FROM inventory
            WHERE barcode = ?
            LIMIT 1
            """,
            (target_barcode,),
        ).fetchone()
        if row is None:
            return False

        previous_amount = _to_float(row["filament_amount"])
        new_amount = _to_float(filament_amount, default=0.0)
        new_amount = round(max(new_amount, 0.0), 2)

        times_logged_out = _to_int(row["times_logged_out"], default=0) + 1
        is_empty = 1 if new_amount <= threshold_value else 0

        updated_roll_weight = _to_float(row["roll_weight"])
        if roll_weight is not None:
            parsed_roll_weight = _to_float(roll_weight)
            if parsed_roll_weight is not None:
                updated_roll_weight = round(parsed_roll_weight, 2)

        conn.execute(
            """
            UPDATE inventory
            SET
                timestamp = ?,
                filament_amount = ?,
                roll_weight = ?,
                times_logged_out = ?,
                is_empty = ?
            WHERE barcode = ?
            """,
            (
                timestamp,
                new_amount,
                updated_roll_weight,
                times_logged_out,
                is_empty,
                target_barcode,
            ),
        )

        delta_used = None
        if previous_amount is not None:
            delta_used = round(max(previous_amount - new_amount, 0.0), 2)

        input_weight_value = None
        if total_weight is not None:
            input_weight_value = round(_to_float(total_weight, default=0.0), 2)

        event_roll_weight = round(updated_roll_weight, 2) if updated_roll_weight is not None else None

        _append_event(
            conn=conn,
            timestamp=timestamp,
            event_type="log_usage",
            barcode=target_barcode,
            brand=row["brand"],
            color=row["color"],
            material=row["material"],
            attr1=row["attribute_1"],
            attr2=row["attribute_2"],
            location=row["location"],
            input_weight=input_weight_value,
            roll_weight=event_roll_weight,
            filament_amount=new_amount,
            delta_used=delta_used,
            times_logged_out=times_logged_out,
            source=source,
        )
        return True

    return False


def add_new_roll_web(
    brand,
    color,
    material,
    attr1,
    attr2,
    location,
    starting_weight,
    filament_amount_target,
    barcode=None,
    source="web",
    empty_threshold=EMPTY_THRESHOLD,
):
    """
    Add a new roll row and append an event log row.
    Returns a dict containing the inserted roll values.
    """
    timestamp = _timestamp_now()
    starting_weight_value = _to_float(starting_weight, default=0.0)
    target_amount = _to_float(filament_amount_target, default=0.0)
    roll_weight = round(starting_weight_value - target_amount, 2)

    if roll_weight < 0:
        raise ValueError("Starting weight must be at least the configured filament amount.")

    filament_amount = round(starting_weight_value - roll_weight, 2)
    threshold_value = _to_float(empty_threshold, default=EMPTY_THRESHOLD)

    brand = normalize_text_case(brand, field="brand")
    color = normalize_text_case(color, field="color")
    material = normalize_text_case(material, field="material")
    attr1 = normalize_text_case(attr1, field="attribute_1")
    attr2 = normalize_text_case(attr2, field="attribute_2")
    location = normalize_text_case(location, field="location")

    if not barcode:
        barcode = generate_barcode.generate_filament_barcode(
            brand,
            color,
            material,
            attr1,
            attr2,
            location,
            sheet=None,
        )

    barcode = str(barcode).strip()
    with open_database(write=True) as conn:
        existing = conn.execute(
            "SELECT 1 FROM inventory WHERE barcode = ? LIMIT 1",
            (barcode,),
        ).fetchone()
        if existing is not None:
            raise ValueError("Barcode already exists. Please retry adding this roll.")

        is_empty = 1 if filament_amount <= threshold_value else 0
        conn.execute(
            """
            INSERT INTO inventory (
                timestamp,
                barcode,
                brand,
                color,
                material,
                attribute_1,
                attribute_2,
                filament_amount,
                location,
                roll_weight,
                times_logged_out,
                is_empty,
                is_favorite
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                timestamp,
                barcode,
                brand,
                color,
                material,
                attr1,
                attr2,
                filament_amount,
                location,
                roll_weight,
                0,
                is_empty,
                0,
            ),
        )

        _append_event(
            conn=conn,
            timestamp=timestamp,
            event_type="new_roll",
            barcode=barcode,
            brand=brand,
            color=color,
            material=material,
            attr1=attr1,
            attr2=attr2,
            location=location,
            input_weight=round(starting_weight_value, 2),
            roll_weight=roll_weight,
            filament_amount=filament_amount,
            delta_used=0,
            times_logged_out=0,
            source=source,
        )

    return {
        "timestamp": timestamp,
        "barcode": barcode,
        "brand": brand,
        "color": color,
        "material": material,
        "attribute_1": attr1,
        "attribute_2": attr2,
        "filament_amount": filament_amount,
        "location": location,
        "roll_weight": roll_weight,
    }


def log_full_filament_data_web(brand, color, material, attr1, attr2, location, starting_weight, roll_weight):
    """
    Backwards-compatible helper retained for older code paths.
    """
    starting = _to_float(starting_weight, default=0.0)
    roll = _to_float(roll_weight, default=0.0)
    target = round(max(starting - roll, 0.0), 2)
    return add_new_roll_web(
        brand=brand,
        color=color,
        material=material,
        attr1=attr1,
        attr2=attr2,
        location=location,
        starting_weight=starting,
        filament_amount_target=target,
        source="legacy",
    )
