import argparse
import sys

from backend.config import DATABASE_PATH, EXCEL_PATH
from backend.workbook_store import convert_excel_to_database


def build_parser():
    parser = argparse.ArgumentParser(
        description="Convert Filament Logs workbook (.xlsx) into SQLite database (.db)."
    )
    parser.add_argument(
        "--xlsx",
        default=EXCEL_PATH,
        help=f"Path to source workbook (default: {EXCEL_PATH})",
    )
    parser.add_argument(
        "--db",
        default=DATABASE_PATH,
        help=f"Path to target SQLite database (default: {DATABASE_PATH})",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace target database if it already exists.",
    )
    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    try:
        result = convert_excel_to_database(
            excel_path=args.xlsx,
            database_path=args.db,
            overwrite=args.overwrite,
        )
    except Exception as exc:
        print(f"Conversion failed: {exc}", file=sys.stderr)
        return 1

    print("Conversion complete.")
    print(f"XLSX: {result['excel_path']}")
    print(f"DB:   {result['database_path']}")
    print(f"Inventory rows: {result['inventory_rows']}")
    print(f"Event rows: {result['event_rows']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
