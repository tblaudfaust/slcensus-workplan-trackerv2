import datetime

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts import permissions
from apps.accounts.models import Role, User
from apps.projects.models import Project, Workstream

from .forms import RestrictedActivityForm
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


class RestrictedFormValidationTests(TestCase):
    def setUp(self):
        self.project, self.workstream = make_project()
        self.activity = Activity.objects.create(
            project=self.project, workstream=self.workstream, name="Task", status=Status.ONGOING
        )

    def test_contributor_cannot_set_completed_directly(self):
        form = RestrictedActivityForm(
            {"status": Status.COMPLETED, "progress_percent": 100, "remarks": ""}, instance=self.activity
        )
        self.assertFalse(form.is_valid())
        self.assertIn("status", form.errors)

    def test_contributor_can_set_pending_validation(self):
        form = RestrictedActivityForm(
            {"status": Status.PENDING_VALIDATION, "progress_percent": 90, "remarks": ""}, instance=self.activity
        )
        self.assertTrue(form.is_valid())

    def test_contributor_can_resave_an_already_completed_activity(self):
        self.activity.status = Status.COMPLETED
        self.activity.save()
        form = RestrictedActivityForm(
            {"status": Status.COMPLETED, "progress_percent": 100, "remarks": "tidy up notes"},
            instance=self.activity,
        )
        self.assertTrue(form.is_valid())


class ValidationWorkflowTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user("admin", password="x", role=Role.ADMIN)
        self.owner = User.objects.create_user("owner", password="x", role=Role.PROJECT_OWNER, email="owner@example.org")
        self.lead = User.objects.create_user("lead", password="pass12345", role=Role.WORKSTREAM_OWNER)
        self.backup = User.objects.create_user("backup", password="pass12345", role=Role.WORKSTREAM_OWNER)
        self.contributor = User.objects.create_user("contrib", password="pass12345", role=Role.CONTRIBUTOR)

        self.project = Project.objects.create(name="Census", owner=self.owner)
        self.workstream = Workstream.objects.create(
            project=self.project, name="GIS", lead=self.lead, backup_lead=self.backup
        )
        self.activity = Activity.objects.create(
            project=self.project,
            workstream=self.workstream,
            name="Finalize frame",
            status=Status.PENDING_VALIDATION,
            responsible=self.contributor,
        )

    def test_lead_can_validate(self):
        self.assertTrue(permissions.can_validate_completion(self.lead, self.activity))

    def test_backup_lead_can_validate(self):
        self.assertTrue(permissions.can_validate_completion(self.backup, self.activity))

    def test_contributor_cannot_validate(self):
        self.assertFalse(permissions.can_validate_completion(self.contributor, self.activity))

    def test_unrelated_workstream_owner_cannot_validate(self):
        other = User.objects.create_user("other_lead", password="x", role=Role.WORKSTREAM_OWNER)
        self.assertFalse(permissions.can_validate_completion(other, self.activity))

    def test_validate_view_marks_completed_and_records_who(self):
        self.client.login(username="lead", password="pass12345")
        response = self.client.post(reverse("activities:validate", args=[self.activity.pk]))
        self.assertEqual(response.status_code, 302)
        self.activity.refresh_from_db()
        self.assertEqual(self.activity.status, Status.COMPLETED)
        self.assertEqual(self.activity.progress_percent, 100)
        self.assertEqual(self.activity.validated_by, self.lead)
        self.assertIsNotNone(self.activity.validated_at)
        self.assertTrue(self.activity.history.filter(field_name="status").exists())

    def test_contributor_cannot_reach_validate_view(self):
        self.client.login(username="contrib", password="pass12345")
        self.client.post(reverse("activities:validate", args=[self.activity.pk]))
        self.activity.refresh_from_db()
        self.assertEqual(self.activity.status, Status.PENDING_VALIDATION)

    def test_validate_is_a_noop_when_not_pending(self):
        self.activity.status = Status.ONGOING
        self.activity.save()
        self.client.login(username="lead", password="pass12345")
        self.client.post(reverse("activities:validate", args=[self.activity.pk]))
        self.activity.refresh_from_db()
        self.assertEqual(self.activity.status, Status.ONGOING)

    def test_send_back_reverts_to_ongoing_and_logs_reason(self):
        self.client.login(username="lead", password="pass12345")
        self.client.post(reverse("activities:send_back", args=[self.activity.pk]), {"reason": "missing sign-off"})
        self.activity.refresh_from_db()
        self.assertEqual(self.activity.status, Status.ONGOING)
        self.assertTrue(self.activity.comments.filter(body__icontains="missing sign-off").exists())
