# ticktick-to-ical

Convert [TickTick](https://ticktick.com/) task exports (CSV) into iCalendar (`.ics`) files compatible with any standard calendar application.

## Overview

TickTick lets you export your tasks as a CSV file. This tool reads that export and produces RFC 5545-compliant `.ics` files — one per task list — so you can import your tasks into apps like Apple Calendar, Google Calendar, Thunderbird, or any other iCalendar-aware client.

**What it handles:**

- Task title, status, and priority
- Due dates and start dates (with full timezone support)
- All-day vs. timed tasks
- Recurring tasks (RRULE)
- Subtasks (as related VTODO components)
- Completion timestamps
- One `.ics` output file per TickTick list

Completed and archived tasks (Status 1 and 2) are skipped by default — only active tasks (Status 0) are exported.

## Requirements

- Python 3.9+
- [`icalendar`](https://pypi.org/project/icalendar/) library

## Installation

```bash
git clone https://github.com/MartinCa/ticktick-to-ical.git
cd ticktick-to-ical
pip install -r requirements.txt
```

## Usage

Export your tasks from TickTick: **Settings → Data Backup → Export**. This downloads a `.csv` file.

```bash
python ticktick_to_ical.py [input] [-o OUTPUT_DIR] [-v]
```

| Argument | Description | Default |
|---|---|---|
| `input` | Path to TickTick CSV export file | `backup.csv` |
| `-o`, `--output-dir` | Directory to write `.ics` files | Current directory |
| `-v`, `--verbose` | Enable debug logging | Off |

### Examples

```bash
# Convert backup.csv in the current directory
python ticktick_to_ical.py

# Specify input file and output directory
python ticktick_to_ical.py ~/Downloads/ticktick_export.csv -o ~/calendars/

# Verbose output for debugging
python ticktick_to_ical.py backup.csv -v
```

The script creates one `.ics` file per TickTick list (e.g. `Work.ics`, `Inbox.ics`). Import these files into your calendar application of choice.

## Running Tests

```bash
python -m unittest discover -s tests
```

## Project Structure

```
ticktick-to-ical/
├── ticktick_to_ical.py        # Main conversion script
├── requirements.txt           # Python dependencies
├── tests/
│   ├── test_ticktick_to_ical.py
│   └── fixtures/
│       └── sample.csv         # Sample TickTick export for tests
└── .github/
    └── workflows/
        └── ci.yml             # GitHub Actions CI
```

## License

See [LICENSE](LICENSE) if present, or check the repository for licensing information.
