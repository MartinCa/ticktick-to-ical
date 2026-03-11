#!/usr/bin/env python3

import argparse
import hashlib
import logging
import re
import sys
from collections import defaultdict
from csv import DictReader
from datetime import datetime, timezone
from itertools import chain
from pathlib import Path
from zoneinfo import ZoneInfo

from icalendar import Calendar, Todo, vRecur


PRIORITY = {"0": 0, "1": 6, "3": 5, "5": 4}

STATUS = {"0": "NEEDS-ACTION", "1": "COMPLETED", "2": "COMPLETED"}

HEADER_MARKER = "Folder Name"

MAX_FILENAME_LEN = 200  # leave room for the .ics extension and filesystem overhead

log = logging.getLogger(__name__)


def parse_iso(value):
    """Parse a TickTick ISO 8601 date string into a UTC datetime.

    Handles arbitrary UTC offsets (e.g. +0000, +0100) via fromisoformat.
    """
    # TickTick uses +0000 without a colon; fromisoformat needs +00:00 on Python <3.11.
    # Python 3.11+ handles both, but we normalise for safety.
    if re.search(r"[+-]\d{4}$", value):
        value = value[:-2] + ":" + value[-2:]
    dt = datetime.fromisoformat(value)
    return dt.astimezone(timezone.utc)


def parse_date(value, tz_name=None, is_all_day=False):
    """Convert a TickTick date string to a Python date or datetime.

    Returns a date object for all-day tasks or when the time resolves to
    midnight in the local timezone.  Returns a UTC datetime otherwise.
    Using proper types lets icalendar emit VALUE=DATE when needed.
    """
    dt_utc = parse_iso(value)

    if is_all_day:
        if tz_name:
            dt_local = dt_utc.astimezone(ZoneInfo(tz_name))
        else:
            dt_local = dt_utc
        return dt_local.date()

    if tz_name:
        dt_local = dt_utc.astimezone(ZoneInfo(tz_name))
        if dt_local.hour == 0 and dt_local.minute == 0 and dt_local.second == 0:
            return dt_local.date()

    return dt_utc


def sanitize_filename(name):
    """Sanitise a string for use as a filename.

    Replaces characters that are unsafe on common filesystems, strips
    leading/trailing dots and spaces, truncates to MAX_FILENAME_LEN,
    and falls back to 'Untitled' for empty names.
    """
    name = re.sub(r'[<>:"/\\|?*]', "_", name)
    name = name.strip(". ")
    name = name[:MAX_FILENAME_LEN]
    return name or "Untitled"


def make_calendar():
    """Create a new calendar with required iCalendar properties."""
    cal = Calendar()
    cal.add("prodid", "-//TickTick Export//EN")
    cal.add("version", "2.0")
    return cal


def parse_subtasks(content):
    """Parse TickTick checklist content into a list of (title, completed) tuples."""
    subtasks = []
    for line in content.splitlines():
        line = line.strip()
        if line.startswith("\u25ab"):
            subtasks.append((line[1:].strip(), False))
        elif line.startswith("\u25aa"):
            subtasks.append((line[1:].strip(), True))
    return subtasks


def _subtask_uid(parent_uid, title):
    """Generate a stable subtask UID based on parent UID and subtask title."""
    digest = hashlib.sha256(title.encode()).hexdigest()[:8]
    return f"{parent_uid}-sub-{digest}"


def build_todo(item):
    """Build a VTODO (and optional subtask VTODOs) from a CSV row.

    Uses icalendar's .add() method throughout so that typed Python objects
    (date, datetime, int) produce correct iCalendar parameters like VALUE=DATE.
    """
    uid = item["taskId"]
    tz_name = item["Timezone"] or None
    is_all_day = item["Is All Day"] == "true"
    created_dt = parse_iso(item["Created Time"])
    status = STATUS.get(item["Status"], "NEEDS-ACTION")
    now = datetime.now(timezone.utc)

    todo = Todo()
    todo.add("uid", uid)
    todo.add("created", now)
    todo.add("summary", item["Title"])

    is_checklist = item["Is Check list"] == "Y"
    subtask_todos = []

    if item["Content"]:
        if is_checklist:
            subtasks = parse_subtasks(item["Content"])
            if subtasks:
                for title, completed in subtasks:
                    sub = Todo()
                    sub.add("uid", _subtask_uid(uid, title))
                    sub.add("created", now)
                    sub.add("summary", title)
                    sub.add("related-to", uid)
                    sub.add("status", "COMPLETED" if completed else "NEEDS-ACTION")
                    sub.add("dtstamp", created_dt)
                    subtask_todos.append(sub)
            else:
                # Checklist flag set but no markers found — preserve as description
                todo.add("description", item["Content"].replace("\r", "\n"))
        else:
            todo.add("description", item["Content"].replace("\r", "\n"))

    if item["Due Date"]:
        todo.add("due", parse_date(item["Due Date"], tz_name, is_all_day))
        if item["Start Date"] and item["Start Date"] != item["Due Date"]:
            todo.add("dtstart", parse_date(item["Start Date"], tz_name, is_all_day))
    elif item["Start Date"]:
        todo.add("dtstart", parse_date(item["Start Date"], tz_name, is_all_day))

    for repeat in item["Repeat"].rstrip().splitlines():
        todo.add("rrule", vRecur.from_ical(repeat))

    todo.add("priority", PRIORITY.get(item["Priority"], 0))
    todo.add("status", status)
    todo.add("dtstamp", created_dt)

    # RFC 5545: COMPLETED must only appear when STATUS is COMPLETED
    if item["Completed Time"] and status == "COMPLETED":
        todo.add("completed", parse_iso(item["Completed Time"]))

    return todo, subtask_todos


def main():
    parser = argparse.ArgumentParser(
        description="Convert a TickTick CSV backup to iCalendar (.ics) files.",
    )
    parser.add_argument(
        "input",
        nargs="?",
        default="backup.csv",
        help="path to the TickTick CSV export (default: backup.csv)",
    )
    parser.add_argument(
        "-o",
        "--output-dir",
        default=".",
        help="directory to write .ics files into (default: current directory)",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="enable verbose logging",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    cals = defaultdict(make_calendar)
    counts = defaultdict(int)  # tasks per list
    skipped = 0

    with open(args.input) as backup:
        # Skip TickTick metadata lines until we reach the CSV header row
        for line in backup:
            if line.startswith(f'"{HEADER_MARKER}"'):
                reader = DictReader(chain([line], backup))
                break
        else:
            log.error("Could not find CSV header row starting with '%s'", HEADER_MARKER)
            sys.exit(1)

        for item in reader:
            # Skip completed (1) and archived (2) items
            if item["Status"] in ("1", "2"):
                skipped += 1
                continue

            list_name = item["List Name"] or "Untitled"
            todo, subtask_todos = build_todo(item)
            cal = cals[list_name]
            cal.add_component(todo)
            counts[list_name] += 1
            for sub in subtask_todos:
                cal.add_component(sub)
                counts[list_name] += 1

    log.info("Skipped %d completed/archived items", skipped)

    for name, cal in cals.items():
        filename = sanitize_filename(name) + ".ics"
        path = output_dir / filename
        log.info("Writing %s (%d VTODOs)", filename, counts[name])
        with open(path, "wb") as out:
            out.write(cal.to_ical())


if __name__ == "__main__":
    main()
