import datetime

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Role, User
from apps.activities.models import Activity, Status
from apps.projects.models import Project, Workstream

from .views import _kpis_from_list, _workstream_performance_from_list


class KpiCalculationTests(TestCase):
    def setUp(self):
        owner = User.objects.create_user("owner", password="x", role=Role.PROJECT_OWNER)
        self.project = Project.objects.create(name="Census", owner=owner)
        self.ws = Workstream.objects.create(project=self.project, name="GIS")
        today = timezone.localdate()

        self.completed = Activity.objects.create(
            project=self.project, workstream=self.ws, name="Done", status=Status.COMPLETED, end_date=today - datetime.timedelta(days=5)
        )
        self.overdue = Activity.objects.create(
            project=self.project, workstream=self.ws, name="Late", status=Status.ONGOING, end_date=today - datetime.timedelta(days=1)
        )
        self.due_soon = Activity.objects.create(
            project=self.project, workstream=self.ws, name="Soon", status=Status.ONGOING, end_date=today + datetime.timedelta(days=3)
        )
        self.unassigned = Activity.objects.create(
            project=self.project, workstream=self.ws, name="NoOwner", status=Status.NOT_STARTED
        )

    def test_totals_and_readiness(self):
        kpis = _kpis_from_list(list(Activity.objects.all()))
        self.assertEqual(kpis["total"], 4)
        self.assertEqual(kpis["status_counts"][Status.COMPLETED], 1)
        self.assertEqual(kpis["readiness"], 25)

    def test_overdue_excludes_completed(self):
        kpis = _kpis_from_list(list(Activity.objects.all()))
        self.assertEqual(kpis["overdue"], 1)

    def test_unassigned_count(self):
        kpis = _kpis_from_list(list(Activity.objects.all()))
        self.assertEqual(kpis["unassigned"], 4)  # none of the 4 activities have an owner set

    def test_due_within_7_days_includes_due_soon_not_overdue(self):
        kpis = _kpis_from_list(list(Activity.objects.all()))
        self.assertEqual(kpis["due_7"], 1)

    def test_workstream_performance_percent(self):
        rows = _workstream_performance_from_list(self.project, list(Activity.objects.all()))
        row = next(r for r in rows if r["workstream"] == self.ws)
        self.assertEqual(row["total"], 4)
        self.assertEqual(row["completed"], 1)
        self.assertEqual(row["percent"], 25)


class DashboardAccessTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("owner", password="pass12345", role=Role.PROJECT_OWNER)
        self.project = Project.objects.create(name="Census", owner=self.owner)

    def test_anonymous_user_redirected_to_login(self):
        response = self.client.get(reverse("dashboard:home"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response.url)

    def test_authenticated_user_sees_dashboard(self):
        self.client.login(username="owner", password="pass12345")
        response = self.client.get(reverse("dashboard:home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Census Readiness Dashboard")

    def test_countdown_card_shown_when_census_day_set(self):
        self.project.census_day = datetime.date(2026, 12, 2)
        self.project.save()
        self.client.login(username="owner", password="pass12345")
        response = self.client.get(reverse("dashboard:home"))
        self.assertContains(response, 'data-countdown-target="2026-12-02"')

    def test_countdown_card_omitted_when_census_day_unset(self):
        self.client.login(username="owner", password="pass12345")
        response = self.client.get(reverse("dashboard:home"))
        self.assertNotContains(response, "data-countdown-target")
