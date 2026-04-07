# Filament Logs

Flask-based inventory tracking for 3D printer filament rolls.
Data is stored in a SQLite database with inventory plus usage event history.

## Features

- Inventory dashboard with search, pagination, favorites, and quick actions
- Log filament usage by barcode with decimal weight support
- Add new rolls with strict mapping-driven dropdowns (brand/color/material/attributes/location)
- Scale integration through `GET /api/scale_weight` (manual entry still supported)
- Event history table (`usage_events`) for time-window popularity analytics
- Settings page for:
  - General/Advanced sections
  - Light/Dark theme
  - Alert handling (`all`, `errors_only`, `silent`, `browser`)
  - Rows per page
  - Default new-roll location
  - Default roll condition (`new`/`used`)
  - Default popularity window (weeks)
  - Configured filament amount for new-roll calculations
  - Adjustable low/empty thresholds
  - Low-stock warning toggle
  - Used-roll map fallback depth + minimum sample count
  - Scale timeout/retry and auto-read on add-roll weight step
  - Negative-filament policy for used-roll mapped weights
  - Optional database auto-backup + retention days
- Optional one-time import from legacy Excel workbook on first database initialization

## Quick Start

1. Create and activate a virtual environment:
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```
2. Install dependencies:
   ```powershell
   pip install flask python-dotenv hidapi
   # Optional (legacy .xlsx import on first DB run):
   pip install openpyxl
   ```
3. Run the app:
   ```powershell
   python GUI/MAIN.py
   ```
4. Open: `http://127.0.0.1:5000`

## XLSX to DB Conversion

Convert an existing workbook into the SQLite format:

```powershell
python GUI/convert_xlsx_to_db.py --xlsx GUI/data/filament_inventory.xlsx --db GUI/data/filament_inventory.db --overwrite
```

Use `--overwrite` only when you want to replace an existing `.db`.

## Data Files

- Inventory database (default): `GUI/data/filament_inventory.db`
- Settings file (default): `GUI/data/settings.json`
- Legacy workbook import source (optional): `GUI/data/filament_inventory.xlsx`
- Mapping files:
  - `GUI/data/brand_mapping.json`
  - `GUI/data/color_mapping.json`
  - `GUI/data/material_mapping.json`
  - `GUI/data/attribute_mapping.json`
  - `GUI/data/weight_mapping.json` (used-roll weight map)

## Environment Variables

- `DATABASE_PATH` (optional): override SQLite database path
- `EXCEL_PATH` (optional): legacy workbook path for first-run import
- `SETTINGS_PATH` (optional): override settings JSON path
- `EMPTY_THRESHOLD` (optional, default `5`): mark roll empty at/below this amount
- `LOW_THRESHOLD` (optional, default `250`): low-stock threshold used by reports/warnings
- `FLASK_SECRET_KEY` (optional): Flask session secret
- `FLASK_DEBUG` (optional, default `1`)

## Notes

- The Flask server must run on the machine connected to the USB scale.
- If the scale is disconnected or unavailable, the app returns a `503` from `/api/scale_weight` and still allows manual entry.
- Browser alert mode requires notification permission in the browser.
