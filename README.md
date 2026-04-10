# Filament Logs

Flask-based inventory tracking for 3D printer filament rolls.
Data is stored in a SQLite database with inventory plus usage event history.

## Features

- Inventory dashboard with search, pagination, favorites, and quick actions
- Log filament usage by barcode with decimal weight support
- Add new rolls with strict mapping-driven dropdowns (brand/color/material/attributes/location)
- Scale integration through `GET /api/scale_weight` (manual entry still supported)
- Event history table (`usage_events`) for time-window popularity analytics
- Usage analytics page with date-window totals and rollups by material and color
- Printable usage report view for browser Print -> Save as PDF
- Popular view can be grouped by roll, brand, color, or brand+color
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
- App version metadata + one-click update checks from Settings
- Built-in bug report form (`/bug_report`) with optional external tracker link
- Brand-based configurable order links for Favorites (`order_links.json`)
- Category-aware color search (e.g., search `blue` to match blue-family shades)
- Edit existing roll details after entry (for correcting mistaken input)
- First-launch setup/tutorial flow (`/welcome`) for initial configuration
- Mapping-aware text normalization preserves canonical material names (`PLA`, `PETG`, `PET-CF`, etc.)
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
- Release/update files:
  - `GUI/data/app_release.json` (local app version + channel metadata)
  - `GUI/data/update_manifest.example.json` (shape for hosted update manifest)
- Bug report files:
  - `GUI/data/bug_reports.jsonl` (newline-delimited bug report submissions)
- Order link files:
  - `GUI/data/order_links.json` (brand-specific order-link templates)

## Environment Variables

- `DATABASE_PATH` (optional): override SQLite database path
- `EXCEL_PATH` (optional): legacy workbook path for first-run import
- `SETTINGS_PATH` (optional): override settings JSON path
- `EMPTY_THRESHOLD` (optional, default `5`): mark roll empty at/below this amount
- `LOW_THRESHOLD` (optional, default `250`): low-stock threshold used by reports/warnings
- `FLASK_SECRET_KEY` (optional): Flask session secret
- `FLASK_DEBUG` (optional, default `1`)
- `APP_RELEASE_PATH` (optional): override release metadata JSON path
- `APP_VERSION` (optional): override runtime app version (`x.y.z`)
- `APP_RELEASE_CHANNEL` (optional, default `stable`): update channel used for checks
- `UPDATE_MANIFEST_URL` (optional): URL to JSON manifest for update checks
- `BUG_REPORTS_PATH` (optional): override path for stored bug report JSONL file
- `BUG_REPORT_URL` (optional): external issue tracker URL shown in the bug report page
- `ORDER_LINKS_PATH` (optional): override path for brand order-link JSON file

## Versioning and Updates

### Local app version metadata

The app reads release info from `GUI/data/app_release.json`:

```json
{
  "version": "0.1.0",
  "release_channel": "stable",
  "released_at": "",
  "notes_url": "",
  "download_url": "",
  "update_manifest_url": ""
}
```

In Settings, the **Version and Updates** card shows the current version and can call `/api/update/check`.

### Release command (bump + manifest output)

Use the release helper to bump or set version numbers and optionally generate a manifest payload:

```powershell
python scripts/release.py --bump patch `
  --download-url "https://example.com/filament-logs/download" `
  --notes-url "https://example.com/filament-logs/releases/1.2.4" `
  --manifest-url "https://example.com/filament-logs/update_manifest.json" `
  --manifest-output "GUI/data/update_manifest.json" `
  --print-manifest
```

You can also set a fixed version directly:

```powershell
python scripts/release.py --set 1.2.4
```

### Deploy/update flow

1. Run `scripts/release.py` to update `app_release.json`.
2. Upload the generated manifest JSON to your hosted `UPDATE_MANIFEST_URL`.
3. Deploy the app update to clients (or publish installer/package if you use one).
4. Clients use Settings -> **Check for Updates** to compare local version against hosted manifest.

## First Launch Setup

On first run, the app opens `/welcome` and asks for common defaults:
- theme, alert mode, rows per page
- default location and roll condition
- configured filament amount and low/empty thresholds

Completing or skipping this flow sets `onboarding_completed` in settings.  
You can re-run it from Settings with **Run Setup Guide**.

## Brand Order Links

Favorites now use brand-aware order links instead of a hardcoded Amazon button.
Configure `GUI/data/order_links.json`:

```json
{
  "default": {
    "label": "Amazon",
    "url_template": "https://www.amazon.com/s?k={query}"
  },
  "brands": {
    "bambu labs": {
      "label": "Bambu Store",
      "url_template": "https://us.store.bambulab.com/search?q={query}"
    }
  }
}
```

Supported URL template placeholders:
- `{query}` (brand + color + material + attributes + "filament")
- `{brand}`, `{color}`, `{material}`, `{attribute_1}`, `{attribute_2}`

## Printable Usage Reports

Open **Usage Stats** and click **Printable PDF Report**.
This opens a print-optimized report page (`/usage_stats/print`) for the current filter range.
Use the browser print dialog and choose **Save as PDF**.

## Notes

- The Flask server must run on the machine connected to the USB scale.
- If the scale is disconnected or unavailable, the app returns a `503` from `/api/scale_weight` and still allows manual entry.
- Browser alert mode requires notification permission in the browser.
