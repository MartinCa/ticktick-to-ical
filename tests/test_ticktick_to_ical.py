#!/usr/bin/env python3

import csv
import os
from datetime import date, datetime, timezone
from itertools import chain
from unittest import TestCase, main

from ticktick_to_ical import (
    build_todo,
    make_calendar,
    parse_date,
    parse_iso,
    parse_subtasks,
    sanitize_filename,
    _subtask_uid,
    HEADER_MARKER,
)


# ---------------------------------------------------------------------------
# Helper: build a CSV row dict with sensible defaults matching sample.csv
# ---------------------------------------------------------------------------
FIELD_DEFAULTS = {
    "Folder Name": "",
    "List Name": "Inbox",
    "Title": "Test task",
    "Kind": "TEXT",
    "Tags": "",
    "Content": "",
    "Is Check list": "N",
    "Start Date": "",
    "Due Date": "",
    "Reminder": "",
    "Repeat": "",
    "Priority": "0",
    "Status": "0",
    "Created Time": "2020-02-24T06:36:53+0000",
    "Completed Time": "",
    "Order": "-456297325527040",
    "Timezone": "Europe/Copenhagen",
    "Is All Day": "true",
    "Is Floating": "false",
    "Column Name": "",
    "Column Order": "",
    "View Mode": "list",
    "taskId": "99999",
    "parentId": "",
}


def make_item(**overrides):
    """Return a dict resembling a parsed CSV row, with overrides applied."""
    item = dict(FIELD_DEFAULTS)
    item.update(overrides)
    return item


# ---------------------------------------------------------------------------
# parse_iso
# ---------------------------------------------------------------------------
class TestParseIso(TestCase):
    def test_utc_offset(self):
        result = parse_iso("2020-02-24T06:36:53+0000")
        self.assertEqual(result, datetime(2020, 2, 24, 6, 36, 53, tzinfo=timezone.utc))

    def test_non_utc_offset(self):
        result = parse_iso("2020-02-24T06:36:53+0100")
        self.assertEqual(result, datetime(2020, 2, 24, 5, 36, 53, tzinfo=timezone.utc))

    def test_negative_offset(self):
        result = parse_iso("2020-02-24T06:36:53-0500")
        self.assertEqual(result, datetime(2020, 2, 24, 11, 36, 53, tzinfo=timezone.utc))

    def test_invalid_format_raises(self):
        with self.assertRaises(ValueError):
            parse_iso("not-a-date")


# ---------------------------------------------------------------------------
# parse_date
# ---------------------------------------------------------------------------
class TestParseDate(TestCase):
    def test_all_day_copenhagen(self):
        result = parse_date(
            "2026-03-14T23:00:00+0000",
            tz_name="Europe/Copenhagen",
            is_all_day=True,
        )
        self.assertEqual(result, date(2026, 3, 15))
        self.assertIsInstance(result, date)
        self.assertNotIsInstance(result, datetime)

    def test_all_day_without_timezone(self):
        result = parse_date(
            "2026-03-14T23:00:00+0000",
            tz_name=None,
            is_all_day=True,
        )
        self.assertEqual(result, date(2026, 3, 14))

    def test_midnight_local_becomes_date_only(self):
        result = parse_date(
            "2026-03-14T23:00:00+0000",
            tz_name="Europe/Copenhagen",
            is_all_day=False,
        )
        self.assertEqual(result, date(2026, 3, 15))
        self.assertNotIsInstance(result, datetime)

    def test_non_midnight_returns_datetime(self):
        result = parse_date(
            "2026-03-14T14:30:00+0000",
            tz_name="Europe/Copenhagen",
            is_all_day=False,
        )
        self.assertIsInstance(result, datetime)
        self.assertEqual(result, datetime(2026, 3, 14, 14, 30, tzinfo=timezone.utc))

    def test_summer_time_offset(self):
        result = parse_date(
            "2026-06-14T22:00:00+0000",
            tz_name="Europe/Copenhagen",
            is_all_day=True,
        )
        self.assertEqual(result, date(2026, 6, 15))

    def test_non_utc_input_offset(self):
        result = parse_date(
            "2026-03-14T23:00:00+0100",
            tz_name="Europe/Copenhagen",
            is_all_day=False,
        )
        # 23:00+0100 = 22:00 UTC → 23:00 CET → not midnight → datetime
        self.assertIsInstance(result, datetime)


# ---------------------------------------------------------------------------
# sanitize_filename
# ---------------------------------------------------------------------------
class TestSanitizeFilename(TestCase):
    def test_clean_name(self):
        self.assertEqual(sanitize_filename("Work"), "Work")

    def test_slash(self):
        self.assertEqual(sanitize_filename("Work/Personal"), "Work_Personal")

    def test_multiple_special_chars(self):
        self.assertEqual(sanitize_filename('A<B>C:D"E'), "A_B_C_D_E")

    def test_empty_string(self):
        self.assertEqual(sanitize_filename(""), "Untitled")

    def test_only_dots(self):
        self.assertEqual(sanitize_filename("..."), "Untitled")

    def test_only_spaces(self):
        self.assertEqual(sanitize_filename("   "), "Untitled")

    def test_leading_trailing_dots_and_spaces(self):
        self.assertEqual(sanitize_filename(" .My List. "), "My List")

    def test_long_name_truncated(self):
        long_name = "A" * 300
        result = sanitize_filename(long_name)
        self.assertLessEqual(len(result), 200)


# ---------------------------------------------------------------------------
# parse_subtasks
# ---------------------------------------------------------------------------
class TestParseSubtasks(TestCase):
    def test_incomplete_subtasks(self):
        content = "\u25abTask A\n\u25abTask B\n"
        result = parse_subtasks(content)
        self.assertEqual(result, [("Task A", False), ("Task B", False)])

    def test_completed_subtasks(self):
        content = "\u25aaTask A\n\u25aaTask B\n"
        result = parse_subtasks(content)
        self.assertEqual(result, [("Task A", True), ("Task B", True)])

    def test_mixed_subtasks(self):
        content = "\u25abIncomplete\n\u25aaComplete\n\u25abAnother incomplete\n"
        result = parse_subtasks(content)
        self.assertEqual(
            result,
            [("Incomplete", False), ("Complete", True), ("Another incomplete", False)],
        )

    def test_empty_lines_ignored(self):
        content = "\u25abTask A\n\n\u25abTask B\n"
        result = parse_subtasks(content)
        self.assertEqual(result, [("Task A", False), ("Task B", False)])

    def test_plain_text_ignored(self):
        content = "Some plain text\n\u25abActual subtask\n"
        result = parse_subtasks(content)
        self.assertEqual(result, [("Actual subtask", False)])

    def test_sample_checklist_content(self):
        """Content matching the active 'Update backup USB' from sample.csv."""
        content = (
            "\u25abExport password manager vault\n"
            "\u25abBackup authenticator app\n"
            "\u25abBackup authenticator unencrypted\n"
            "\u25abNAS configuration\n"
            "\u25abEncrypted volumes\n"
            "\u25abBootable USB tool\n"
            "\u25abOS images\n"
            "\u25abRemove old backups\n"
            "\u25abSync cloud storage\n"
            "\u25abUpdate encryption tool binaries\n"
        )
        result = parse_subtasks(content)
        self.assertEqual(len(result), 10)
        self.assertTrue(all(not completed for _, completed in result))
        self.assertEqual(result[0][0], "Export password manager vault")
        self.assertEqual(result[3][0], "NAS configuration")

    def test_completed_sample_content(self):
        """Content matching the archived 'Update backup USB' instances."""
        content = (
            "\u25aaSync cloud storage\n"
            "\u25aaRemove old backups\n"
            "\u25aaBackup authenticator unencrypted\n"
        )
        result = parse_subtasks(content)
        self.assertEqual(len(result), 3)
        self.assertTrue(all(completed for _, completed in result))

    def test_returns_empty_for_plain_text(self):
        content = "Just some notes\nAnother line\n"
        result = parse_subtasks(content)
        self.assertEqual(result, [])


# ---------------------------------------------------------------------------
# _subtask_uid
# ---------------------------------------------------------------------------
class TestSubtaskUid(TestCase):
    def test_stable_across_calls(self):
        uid1 = _subtask_uid("100", "Buy milk")
        uid2 = _subtask_uid("100", "Buy milk")
        self.assertEqual(uid1, uid2)

    def test_different_titles_different_uids(self):
        uid1 = _subtask_uid("100", "Buy milk")
        uid2 = _subtask_uid("100", "Buy bread")
        self.assertNotEqual(uid1, uid2)

    def test_different_parents_different_uids(self):
        uid1 = _subtask_uid("100", "Buy milk")
        uid2 = _subtask_uid("200", "Buy milk")
        self.assertNotEqual(uid1, uid2)

    def test_format(self):
        uid = _subtask_uid("100", "Buy milk")
        self.assertTrue(uid.startswith("100-sub-"))
        self.assertEqual(len(uid.split("-sub-")[1]), 8)


# ---------------------------------------------------------------------------
# build_todo
# ---------------------------------------------------------------------------
class TestBuildTodo(TestCase):
    def test_basic_task(self):
        item = make_item(Title="Simple task", taskId="100")
        todo, subtasks = build_todo(item)
        self.assertEqual(str(todo["uid"]), "100")
        self.assertEqual(str(todo["summary"]), "Simple task")
        self.assertEqual(str(todo["status"]), "NEEDS-ACTION")
        self.assertEqual(subtasks, [])

    def test_all_day_due_date_produces_value_date(self):
        item = make_item(
            **{
                "Due Date": "2026-03-14T23:00:00+0000",
                "Start Date": "2026-03-14T23:00:00+0000",
                "Is All Day": "true",
                "Timezone": "Europe/Copenhagen",
            }
        )
        todo, _ = build_todo(item)
        ical = todo.to_ical().decode()
        self.assertIn("DUE;VALUE=DATE:20260315", ical)

    def test_non_all_day_due_date_has_no_value_date(self):
        item = make_item(
            **{
                "Due Date": "2026-03-14T14:30:00+0000",
                "Start Date": "",
                "Is All Day": "false",
                "Timezone": "Europe/Copenhagen",
            }
        )
        todo, _ = build_todo(item)
        ical = todo.to_ical().decode()
        self.assertIn("DUE:20260314T143000Z", ical)

    def test_start_date_omitted_when_equal_to_due(self):
        item = make_item(
            **{
                "Due Date": "2026-03-14T23:00:00+0000",
                "Start Date": "2026-03-14T23:00:00+0000",
            }
        )
        todo, _ = build_todo(item)
        ical = todo.to_ical().decode()
        self.assertIn("DUE", ical)
        self.assertNotIn("DTSTART", ical)

    def test_start_date_kept_when_different(self):
        item = make_item(
            **{
                "Due Date": "2026-03-14T23:00:00+0000",
                "Start Date": "2026-03-10T23:00:00+0000",
            }
        )
        todo, _ = build_todo(item)
        ical = todo.to_ical().decode()
        self.assertIn("DUE", ical)
        self.assertIn("DTSTART", ical)

    def test_checklist_produces_subtasks(self):
        item = make_item(
            **{
                "Is Check list": "Y",
                "Kind": "CHECKLIST",
                "Content": "\u25abSub A\n\u25abSub B\n\u25aaSub C\n",
                "taskId": "200",
            }
        )
        todo, subtasks = build_todo(item)
        self.assertEqual(len(subtasks), 3)
        self.assertNotIn("description", todo)
        for sub in subtasks:
            self.assertEqual(str(sub["related-to"]), "200")
        self.assertEqual(str(subtasks[0]["status"]), "NEEDS-ACTION")
        self.assertEqual(str(subtasks[1]["status"]), "NEEDS-ACTION")
        self.assertEqual(str(subtasks[2]["status"]), "COMPLETED")

    def test_checklist_without_markers_falls_back_to_description(self):
        item = make_item(
            **{
                "Is Check list": "Y",
                "Content": "Just some notes without markers\nAnother line\n",
                "taskId": "300",
            }
        )
        todo, subtasks = build_todo(item)
        self.assertEqual(subtasks, [])
        self.assertIn("description", todo)
        self.assertIn("Just some notes", str(todo["description"]))

    def test_subtask_uids_are_stable(self):
        item = make_item(
            **{
                "Is Check list": "Y",
                "Content": "\u25abAlpha\n\u25abBeta\n",
                "taskId": "400",
            }
        )
        _, subs1 = build_todo(item)
        _, subs2 = build_todo(item)
        self.assertEqual(str(subs1[0]["uid"]), str(subs2[0]["uid"]))
        self.assertEqual(str(subs1[1]["uid"]), str(subs2[1]["uid"]))

    def test_non_checklist_content_becomes_description(self):
        item = make_item(
            Content="https://example.com/some-link",
            **{"Is Check list": "N"},
        )
        todo, subtasks = build_todo(item)
        self.assertEqual(str(todo["description"]), "https://example.com/some-link")
        self.assertEqual(subtasks, [])

    def test_rrule_parsed(self):
        item = make_item(Repeat="FREQ=MONTHLY;INTERVAL=1;BYDAY=3SU")
        todo, _ = build_todo(item)
        ical = todo.to_ical().decode()
        self.assertIn("RRULE:FREQ=MONTHLY", ical)

    def test_no_rrule_when_empty(self):
        item = make_item(Repeat="")
        todo, _ = build_todo(item)
        ical = todo.to_ical().decode()
        self.assertNotIn("RRULE", ical)

    def test_unknown_priority_defaults(self):
        item = make_item(Priority="9")
        todo, _ = build_todo(item)
        self.assertEqual(int(todo["priority"]), 0)

    def test_unknown_status_defaults(self):
        item = make_item(Status="7")
        todo, _ = build_todo(item)
        self.assertEqual(str(todo["status"]), "NEEDS-ACTION")

    def test_completed_time_set_when_status_completed(self):
        item = make_item(
            Status="1",
            **{"Completed Time": "2026-02-15T17:39:33+0000"},
        )
        todo, _ = build_todo(item)
        ical = todo.to_ical().decode()
        self.assertIn("COMPLETED:20260215T173933Z", ical)

    def test_completed_time_omitted_when_status_active(self):
        """RFC 5545: COMPLETED must only appear when STATUS is COMPLETED."""
        item = make_item(
            Status="0",
            **{"Completed Time": "2020-03-15T18:36:58+0000"},
        )
        todo, _ = build_todo(item)
        ical = todo.to_ical().decode()
        self.assertNotIn("COMPLETED", ical)
        self.assertIn("STATUS:NEEDS-ACTION", ical)

    def test_completed_time_absent(self):
        item = make_item(**{"Completed Time": ""})
        todo, _ = build_todo(item)
        ical = todo.to_ical().decode()
        self.assertNotIn("COMPLETED", ical)

    def test_priority_is_integer_in_output(self):
        item = make_item(Priority="1")
        todo, _ = build_todo(item)
        ical = todo.to_ical().decode()
        self.assertIn("PRIORITY:6", ical)


# ---------------------------------------------------------------------------
# make_calendar
# ---------------------------------------------------------------------------
class TestMakeCalendar(TestCase):
    def test_has_required_properties(self):
        cal = make_calendar()
        ical = cal.to_ical().decode()
        self.assertIn("PRODID", ical)
        self.assertIn("VERSION:2.0", ical)


# ---------------------------------------------------------------------------
# Integration test against sample.csv
# ---------------------------------------------------------------------------
class TestFullExportWithSampleCSV(TestCase):
    """Run the full pipeline against the shipped sample.csv."""

    @classmethod
    def setUpClass(cls):
        from collections import defaultdict

        cls.cals = defaultdict(make_calendar)
        cls.active_items = []

        sample_path = os.path.join(os.path.dirname(__file__), "sample.csv")
        with open(sample_path) as backup:
            for line in backup:
                if line.startswith(f'"{HEADER_MARKER}"'):
                    reader = csv.DictReader(chain([line], backup))
                    break
            else:
                raise ValueError("Could not find CSV header row")

            for item in reader:
                if item["Status"] in ("1", "2"):
                    continue
                cls.active_items.append(item)
                todo, subtask_todos = build_todo(item)
                list_name = item["List Name"] or "Untitled"
                cal = cls.cals[list_name]
                cal.add_component(todo)
                for sub in subtask_todos:
                    cal.add_component(sub)

        cls.inbox_ical = cls.cals["Inbox"].to_ical().decode()

    def test_only_active_items_exported(self):
        self.assertEqual(len(self.active_items), 1)
        self.assertEqual(self.active_items[0]["taskId"], "26378")
        self.assertEqual(self.active_items[0]["Title"], "Update backup USB")

    def test_only_inbox_calendar_created(self):
        self.assertEqual(list(self.cals.keys()), ["Inbox"])

    def test_update_backup_usb_is_present(self):
        self.assertIn("Update backup USB", self.inbox_ical)

    def test_due_date_is_date_only_with_value_param(self):
        self.assertIn("DUE;VALUE=DATE:20260315", self.inbox_ical)

    def test_no_dtstart_when_same_as_due(self):
        self.assertNotIn("DTSTART", self.inbox_ical)

    def test_rrule_present(self):
        self.assertIn("RRULE:FREQ=MONTHLY", self.inbox_ical)
        self.assertIn("BYDAY=3SU", self.inbox_ical)

    def test_subtask_count(self):
        self.assertEqual(self.inbox_ical.count("RELATED-TO:26378"), 10)

    def test_subtask_summaries(self):
        expected = [
            "Export password manager vault",
            "Backup authenticator unencrypted",
            "NAS configuration",
            "Encrypted volumes",
            "Bootable USB tool",
            "OS images",
            "Remove old backups",
        ]
        for name in expected:
            self.assertIn(name, self.inbox_ical)

    def test_no_completed_on_active_task(self):
        """The active Update backup USB has a Completed Time from a prior
        recurrence, but STATUS is 0 (NEEDS-ACTION) so COMPLETED must not appear
        on the parent VTODO."""
        blocks = self.inbox_ical.split("BEGIN:VTODO")
        for block in blocks:
            if "Update backup USB" in block:
                self.assertNotIn("COMPLETED:", block)
                break

    def test_completed_archived_excluded(self):
        self.assertNotIn("Play Portal Stories: Mel", self.inbox_ical)
        self.assertNotIn("Discard old hard drive", self.inbox_ical)
        self.assertNotIn("Try Joplin note app", self.inbox_ical)

    def test_work_list_not_created(self):
        self.assertNotIn("Work", self.cals)

    def test_valid_ical_structure(self):
        self.assertTrue(self.inbox_ical.startswith("BEGIN:VCALENDAR"))
        self.assertTrue(self.inbox_ical.rstrip().endswith("END:VCALENDAR"))
        self.assertIn("VERSION:2.0", self.inbox_ical)
        self.assertIn("PRODID:-//TickTick Export//EN", self.inbox_ical)

    def test_all_vtodos_have_dtstamp(self):
        vtodo_count = self.inbox_ical.count("BEGIN:VTODO")
        dtstamp_count = self.inbox_ical.count("DTSTAMP:")
        self.assertEqual(vtodo_count, dtstamp_count)

    def test_no_raw_string_dates(self):
        for line in self.inbox_ical.splitlines():
            if line.startswith("DUE:") or line.startswith("DTSTART:"):
                value = line.split(":", 1)[1]
                self.assertIn("T", value, f"Date-only value without VALUE=DATE: {line}")


if __name__ == "__main__":
    main()
