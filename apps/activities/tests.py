import datetime

from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import Role, User
from apps.projects.models import Project, Workstream

from .models import Activity, Status
from .services import record_changes, snapshot


def make_project():
    owner = User.objects.create_user("owner", password="x", role=Role.PROJECT_OWNER)
    project = Project.objects.create(name="Test Census", owner=owner)
    workstream = Workstream.objects.create(project=project, name="GIS")
    return project, workstream


class ActivityModelTests(TestCase):
    def setUp(self):
        self.project, self.workstream = make_project()

    def test_duration_auto_computed_from_dates(self):
        activity = Activity.objects.create(
            project=self.project,
            workstream=self.workstream,
            name="Map EAs",
            start_date=datetime.date(2026, 1, 1),
            end_date=datetime.date(2026, 1, 10),
        )
        self.assertEqual(activity.duration_days, 10)

    def test_explicit_duration_is_not_overwritten(self):
        activity = Activity.objects.create(
            project=self.project,
            workstream=self.workstream,
            name="Map EAs",
            start_date=datetime.date(2026, 1, 1),
            end_date=datetime.date(2026, 1, 10),
            duration_days=99,
        )
        self.assertEqual(activity.duration_days, 99)

    def test_is_overdue_true_for_past_end_date_and_open_status(self):
        activity = Activity.objects.create(
            project=self.project,
            workstream=self.workstream,
            name="Late task",
            end_date=timezone.localdate() - datetime.timedelta(days=1),
            status=Status.ONGOING,
        )
        self.assertTrue(activity.is_overdue)

    def test_is_overdue_false_when_completed(self):
        activity = Activity.objects.create(
            project=self.project,
            workstream=self.workstream,
            name="Finished task",
            end_date=timezone.localdate() - datetime.timedelta(days=1),
            status=Status.COMPLETED,
        )
        self.assertFalse(activity.is_overdue)

    def test_source_row_key_matches_same_workstream_and_name(self):
        key1 = Activity.build_row_key(self.workstream.id, "Recruit supervisors")
        key2 = Activity.build_row_key(self.workstream.id, "  recruit   supervisors  ")
        self.assertEqual(key1, key2)

    def test_source_row_key_differs_across_workstreams(self):
        other_ws = Workstream.objects.create(project=self.project, name="HR")
        key1 = Activity.build_row_key(self.workstream.id, "Recruit supervisors")
        key2 = Activity.build_row_key(other_ws.id, "Recruit supervisors")
        self.assertNotEqual(key1, key2)

    def test_has_owner_true_for_free_text_responsible(self):
        activity = Activity.objects.create(
            project=self.project, workstream=self.workstream, name="X", responsible_text="External consultant"
        )
        self.assertTrue(activity.has_owner)

    def test_has_owner_false_when_unassigned(self):
        activity = Activity.objects.create(project=self.project, workstream=self.workstream, name="X")
        self.assertFalse(activity.has_owner)


class RecordChangesTests(TestCase):
    def setUp(self):
        self.project, self.workstream = make_project()
        self.activity = Activity.objects.create(
            project=self.project, workstream=self.workstream, name="Task", status=Status.NOT_STARTED
        )

    def test_no_changes_returns_empty_dict(self):
        before = snapshot(self.activity)
        changed = record_changes(self.activity, before)
        self.assertEqual(changed, {})
        self.assertEqual(self.activity.history.count(), 0)

    def test_status_change_is_recorded_with_display_values(self):
        before = snapshot(self.activity)
        self.activity.status = Status.COMPLETED
        self.activity.save()
        changed = record_changes(self.activity, before)
        self.assertIn("status", changed)
        old_display, new_display = changed["status"]
        self.assertEqual(old_display, "Not Started")
        self.assertEqual(new_display, "Completed")
        self.assertEqual(self.activity.history.count(), 1)
