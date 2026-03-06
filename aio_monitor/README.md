# AI Overview Monitor

A lightweight, scheduled workflow that monitors Google SERPs for AI Overviews. It searches Google for each keyword in your list, detects whether an AI Overview is present, captures a screenshot, extracts cited domains, and flags whether your target domains are cited.

## Architecture

```
┌──────────────────────────────────────────────────┐
│                   run.py (CLI)                   │
├──────────────────────────────────────────────────┤
│              orchestrator.py                     │
│  ┌─────────┐  ┌──────────┐  ┌────────────────┐  │
│  │ Browser  │  │  Storage │  │   Reporting    │  │
│  │ Engine   │  │ Backend  │  │   Generator    │  │
│  │(abstract)│  │(abstract)│  │  (MD + HTML)   │  │
│  ├─────────┤  ├──────────┤  └────────────────┘  │
│  │OpenClaw │  │  SQLite  │                       │
│  │Playwright│ │(→BigQuery)│                      │
│  │Selenium │  └──────────┘                       │
│  └─────────┘                                     │
├──────────────────────────────────────────────────┤
│              serp_checker.py                     │
│  Google Search → AI Overview Detection →         │
│  Screenshot → Citation Extraction                │
└──────────────────────────────────────────────────┘
```

## Quick Start

### 1. Install dependencies

```bash
pip install -r requirements.txt

# If using Playwright engine:
playwright install chromium

# If using OpenClaw engine:
npm install -g openclaw@latest
openclaw browser install
```

### 2. Configure

Edit `aio_monitor/config/config.yaml`:

```yaml
# Set your target domains
target_domains:
  - "yourdomain.com"
  - "www.yourdomain.com"

# Choose browser engine: "openclaw", "playwright", or "selenium"
browser_engine: "openclaw"

# Add your keywords to aio_monitor/config/keywords.txt
```

### 3. Add keywords

Edit `aio_monitor/config/keywords.txt` (one keyword per line):

```
best project management software
how to improve website speed
what is semantic SEO
```

### 4. Run

```bash
python run.py
```

## Usage

```bash
# Run with default config
python run.py

# Use a custom config file
python run.py --config path/to/config.yaml

# Run for a specific date (backfill)
python run.py --date 2026-03-01

# Export results to CSV
python run.py --export-csv 2026-03-01
```

## Output Structure

```
output/
├── aio_monitor.db              # SQLite database (all results)
├── aio_monitor.log             # Run log
├── screenshots/
│   └── 2026-03-06/             # Dated screenshot folders
│       ├── best_project_management_software_143022.png
│       └── how_to_improve_website_speed_143045.png
└── reports/
    ├── report_2026-03-06.md    # Markdown daily report
    ├── report_2026-03-06.html  # HTML daily report
    └── results_2026-03-06.csv  # CSV export
```

## Per-Keyword Output Fields

| Field | Type | Description |
|-------|------|-------------|
| `keyword` | string | The search keyword |
| `checked_at` | ISO datetime | When the check was performed |
| `ai_overview_present` | boolean | Whether an AI Overview was detected |
| `cited_domains` | JSON list | Domains cited in the AI Overview |
| `target_domain_cited` | boolean | Whether any target domain was cited |
| `screenshot_path` | string | Path to the SERP screenshot |
| `notes` | string | Detection notes, raw observations, errors |
| `run_status` | string | `success`, `failed`, or `partial` |

## Browser Engines

### OpenClaw (recommended)
Uses OpenClaw's managed browser — an isolated Chromium instance controlled via CLI. Best for daily automated monitoring.

### Playwright
Headless Chromium via Playwright. Good fallback when OpenClaw isn't installed.

### Selenium
Headless Chrome via Selenium + ChromeDriver. Universal fallback that works anywhere Chrome is installed.

Set the engine in `config.yaml`:
```yaml
browser_engine: "openclaw"   # or "playwright" or "selenium"
```

## Scheduling (Cron)

Add to crontab for daily runs:

```bash
# Run daily at 6 AM UTC
0 6 * * * cd /path/to/search-intelligence-platform && /path/to/python run.py >> /var/log/aio-monitor.log 2>&1
```

Or use systemd timers, Windows Task Scheduler, or any job scheduler.

## Storage Layer

The storage layer uses an abstract interface (`StorageBackend`) so it can be swapped to BigQuery, PostgreSQL, or any other database. Currently ships with SQLite.

To implement a new backend, subclass `aio_monitor.storage.base.StorageBackend` and implement the required methods:
- `initialize()` — create tables/schema
- `save_result()` / `save_results()` — persist results
- `get_results_by_date()` — query by date
- `get_latest_result()` — query by keyword
- `export_csv()` — export to CSV
- `close()` — cleanup

## AI Overview Detection

Detection uses multiple strategies:
1. **CSS selector matching** — checks for known AI Overview container elements
2. **Page source analysis** — scans HTML for AI Overview text patterns and data attributes
3. **Screenshot capture** — always taken for manual verification

**Important:** Google's DOM structure changes frequently. If detection becomes unreliable, the system stores raw notes and screenshot paths for manual review rather than faking results. Update the selectors in `serp_checker.py` as Google's markup evolves.

## Configuration Reference

See `aio_monitor/config/config.yaml` for the full configuration with comments.
