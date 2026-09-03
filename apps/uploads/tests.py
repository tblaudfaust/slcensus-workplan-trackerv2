import datetime
import io

import pandas as pd
from django.test import TestCase

from apps.accounts.models import Role, User
from apps.activities.models import Activity, Status
from apps.projects.models import Project, Workstream

from .parsing import _promote_header_row, match_columns, normalize_header, normalize_status_text, parse_sheet
from .services import commit_upload


class ColumnMatchingTests(TestCase):
    def test_exact_alias_matches(self):
        headers = ["Milestone/Activity", "Start Date", "End Date", "Responsible Person/Team Contact"]
        mapping, unmatched = match_columns(headers)
        self.assertEqual(mapping["name"], "Milestone/Activity")
        self.assertEqual(mapping["start_date"], "Start Date")
        self.assertEqual(mapping["responsible"], "Responsible Person/Team Contact")
        self.assertEqual(unmatched, [])

    def test_fuzzy_match_for_slightly_different_header(self):
        # "Team Contact Person" isn't a literal alias but should still map to
        # responsible via the fuzzy pass rather than being left unmatched.
        headers = ["Activity", "Team Contact Person"]
        mapping, unmatched = match_columns(headers)
        self.assertEqual(mapping.get("responsible"), "Team Contact Person")

    def test_unrelated_header_is_left_unmatched(self):
        headers = ["Activity", "Internal Budget Code XYZ123"]
        mapping, unmatched = match_columns(headers)
        self.assertIn("Internal Budget Code XYZ123", unmatched)

    def test_normalize_header_strips_punctuation_and_case(self):
        self.assertEqual(normalize_header("Deliverable / Expected Output"), "deliverable expected output")


class StatusNormalizationTests(TestCase):
    def test_completed_keyword(self):
        status, progress = normalize_status_text("Completed")
        self.assertEqual(status, "COMPLETED")
        self.assertEqual(progress, 100)

    def test_percentage_extracted(self):
        status, progress = normalize_status_text("Ongoing - 65% done")
        self.assertEqual(status, "ONGOING")
        self.assertEqual(progress, 65)

    def test_empty_text_is_not_started(self):
        status, progress = normalize_status_text("")
        self.assertEqual(status, "NOT_STARTED")
        self.assertEqual(progress, 0)

    def test_unrecognized_text_defaults_to_ongoing(self):
        status, progress = normalize_status_text("Awaiting budget clarification from the Ministry")
        self.assertEqual(status, "ONGOING")

    def test_pending_maps_to_not_started(self):
        status, progress = normalize_status_text("Pending review from HQ")
        self.assertEqual(status, "NOT_STARTED")


class PromoteHeaderRowTests(TestCase):
    def test_well_formed_sheet_uses_row_zero_as_header(self):
        raw = pd.DataFrame(
            [
                ["Milestone / Activity", "Start Date", "End Date"],
                ["Task A", "2026-01-01", "2026-01-10"],
            ]
        )
        result = _promote_header_row(raw)
        self.assertEqual(list(result.columns), ["Milestone / Activity", "Start Date", "End Date"])
        self.assertEqual(len(result), 1)

    def test_title_row_above_header_is_detected_and_skipped(self):
        raw = pd.DataFrame(
            [
                ["STATISTICS SIERRA LEONE, 2026 PHC WORKPLAN", "", "", ""],
                ["", "", "", ""],
                ["No.", "Milestone / Activity", "Start Date", "End Date"],
                ["1", "Task A", "2026-01-01", "2026-01-10"],
            ]
        )
        result = _promote_header_row(raw)
        self.assertIn("Milestone / Activity", list(result.columns))
        self.assertEqual(len(result), 1)
        self.assertEqual(result.iloc[0]["Milestone / Activity"], "Task A")

    def test_sheet_with_no_recognizable_header_falls_back_to_row_zero(self):
        raw = pd.DataFrame([["Foo", "Bar"], ["1", "2"]])
        result = _promote_header_row(raw)
        self.assertEqual(list(result.columns), ["Foo", "Bar"])


class ParseSheetTests(TestCase):
    def test_blank_row_is_skipped_not_errored(self):
        df = pd.DataFrame({"Activity": ["Task A", ""], "End Date": ["2026-01-01", ""]})
        mapping = {"name": "Activity", "end_date": "End Date"}
        rows = parse_sheet(df, mapping, default_workstream_name="GIS")
        self.assertEqual(len(rows), 1)

    def test_missing_name_with_other_data_is_an_error(self):
        df = pd.DataFrame({"Activity": [""], "Deliverable": ["Some output"]})
        mapping = {"name": "Activity", "deliverable": "Deliverable"}
        rows = parse_sheet(df, mapping, default_workstream_name="GIS")
        self.assertEqual(len(rows), 1)
        self.assertFalse(rows[0].is_valid)

    def test_end_before_start_is_an_error(self):
        df = pd.DataFrame({"Activity": ["Task"], "Start Date": ["2026-02-01"], "End Date": ["2026-01-01"]})
        mapping = {"name": "Activity", "start_date": "Start Date", "end_date": "End Date"}
        rows = parse_sheet(df, mapping, default_workstream_name="GIS")
        self.assertFalse(rows[0].is_valid)

    def test_default_workstream_used_when_no_workstream_column(self):
        df = pd.DataFrame({"Activity": ["Task"]})
        rows = parse_sheet(df, {"name": "Activity"}, default_workstream_name="Publicity")
        self.assertEqual(rows[0].data["workstream_name"], "Publicity")


class CommitUploadTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("owner", password="x", role=Role.PROJECT_OWNER)
        self.project = Project.objects.create(name="Census", owner=self.owner)
        self.responsible = User.objects.create_user(
            "wkamara", password="x", first_name="Wusu", last_name="Kamara", email="w@example.org"
        )

    def _sheets(self, rows):
        df = pd.DataFrame(rows)
        return {"GIS": df}

    def test_creates_new_activity(self):
        sheets = self._sheets(
            {
                "Milestone/Activity": ["Finalize EA boundaries"],
                "Start Date": ["2026-01-01"],
                "End Date": ["2026-02-01"],
                "Responsible Person/Team Contact": ["Wusu Kamara"],
                "Status/Remark": ["Ongoing 40%"],
            }
        )
        mapping = {
            "GIS": {
                "name": "Milestone/Activity",
                "start_date": "Start Date",
                "end_date": "End Date",
                "responsible": "Responsible Person/Team Contact",
                "status": "Status/Remark",
            }
        }
        batch = commit_upload(
            project=self.project,
            workstream_override=None,
            sheets=sheets,
            mapping=mapping,
            uploaded_by=self.owner,
            file_name="test.xlsx",
        )
        self.assertEqual(batch.rows_created, 1)
        activity = Activity.objects.get()
        self.assertEqual(activity.workstream.name, "GIS")
        self.assertEqual(activity.status, Status.ONGOING)
        self.assertEqual(activity.progress_percent, 40)
        self.assertEqual(activity.responsible, self.responsible)

    def test_reupload_updates_instead_of_duplicating(self):
        sheets = self._sheets(
            {"Milestone/Activity": ["Finalize EA boundaries"], "Status/Remark": ["Ongoing 40%"]}
        )
        mapping = {"GIS": {"name": "Milestone/Activity", "status": "Status/Remark"}}
        commit_upload(
            project=self.project, workstream_override=None, sheets=sheets, mapping=mapping,
            uploaded_by=self.owner, file_name="a.xlsx",
        )

        sheets2 = self._sheets(
            {"Milestone/Activity": ["Finalize EA boundaries"], "Status/Remark": ["Completed"]}
        )
        batch2 = commit_upload(
            project=self.project, workstream_override=None, sheets=sheets2, mapping=mapping,
            uploaded_by=self.owner, file_name="b.xlsx",
        )

        self.assertEqual(Activity.objects.count(), 1)
        self.assertEqual(batch2.rows_created, 0)
        self.assertEqual(batch2.rows_updated, 1)
        activity = Activity.objects.get()
        self.assertEqual(activity.status, Status.COMPLETED)
        self.assertEqual(activity.history.filter(field_name="status").count(), 1)

    def test_invalid_row_is_skipped_and_reported(self):
        sheets = self._sheets({"Milestone/Activity": [""], "Deliverable": ["Some output"]})
        mapping = {"GIS": {"name": "Milestone/Activity", "deliverable": "Deliverable"}}
        batch = commit_upload(
            project=self.project, workstream_override=None, sheets=sheets, mapping=mapping,
            uploaded_by=self.owner, file_name="bad.xlsx",
        )
        self.assertEqual(batch.rows_skipped, 1)
        self.assertEqual(Activity.objects.count(), 0)
        self.assertEqual(len(batch.errors), 1)

    def test_workstream_override_used_regardless_of_sheet_name(self):
        override = Workstream.objects.create(project=self.project, name="Publicity")
        sheets = self._sheets({"Milestone/Activity": ["Launch campaign"]})
        mapping = {"GIS": {"name": "Milestone/Activity"}}
        commit_upload(
            project=self.project, workstream_override=override, sheets=sheets, mapping=mapping,
            uploaded_by=self.owner, file_name="c.xlsx",
        )
        activity = Activity.objects.get()
        self.assertEqual(activity.workstream, override)
