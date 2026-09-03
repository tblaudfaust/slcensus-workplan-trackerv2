from django.core import mail
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import Role, User
from apps.activities.models import Activity, Status
from apps.notifications.models import NotificationLog, RuleType

from .models import Project, Workstream


class WorkstreamPercentCompleteTests(TestCase):
    def setUp(self):
        owner = User.objects.create_user("owner", password="x", role=Role.PROJECT_OWNER)
        self.project = Project.objects.create(name="Census", owner=owner)
        self.ws = Workstream.objects.create(project=self.project, name="GIS")

    def test_zero_activities_is_zero_percent(self):
        self.assertEqual(self.ws.percent_complete, 0)

    def test_percent_rounds_to_nearest_whole_number(self):
        Activity.objects.create(project=self.project, workstream=self.ws, name="a", status=Status.COMPLETED)
        Activity.objects.create(project=self.project, workstream=self.ws, name="b", status=Status.ONGOING)
        Activity.objects.create(project=self.project, workstream=self.ws, name="c", status=Status.ONGOING)
        self.assertEqual(self.ws.percent_complete, 33)

    def test_unique_together_project_and_name(self):
        Workstream.objects.create(project=self.project, name="HR")
        with self.assertRaises(Exception):
            Workstream.objects.create(project=self.project, name="HR")


class ManualAlertTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            "owner", password="x", role=Role.PROJECT_OWNER, email="owner@example.org"
        )
        self.lead = User.objects.create_user(
            "lead", password="pass12345", role=Role.WORKSTREAM_OWNER, email="lead@example.org"
        )
        self.contributor = User.objects.create_user("contrib", password="pass12345", role=Role.CONTRIBUTOR)
        self.project = Project.objects.create(name="Census", owner=self.owner)
        self.ws = Workstream.objects.create(project=self.project, name="GIS", lead=self.lead)
        Activity.objects.create(project=self.project, workstream=self.ws, name="Task", status=Status.ONGOING)

    def test_lead_can_send_alert_to_lead_and_owner(self):
        self.client.login(username="lead", password="pass12345")
        response = self.client.post(
            reverse("projects:workstream_alert", args=[self.ws.pk]), {"message": "please review"}
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(mail.outbox), 2)
        self.assertTrue(NotificationLog.objects.filter(rule_type=RuleType.MANUAL_ALERT).exists())

    def test_contributor_cannot_send_alert(self):
        self.client.login(username="contrib", password="pass12345")
        self.client.post(reverse("projects:workstream_alert", args=[self.ws.pk]), {"message": "hi"})
        self.assertEqual(len(mail.outbox), 0)


class NavWorkstreamsContextTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("owner", password="pass12345", role=Role.PROJECT_OWNER)
        self.project = Project.objects.create(name="Census", owner=self.owner)
        Workstream.objects.create(project=self.project, name="GIS")
        Workstream.objects.create(project=self.project, name="HR")

    def test_navbar_lists_active_projects_workstreams(self):
        self.client.login(username="owner", password="pass12345")
        response = self.client.get(reverse("dashboard:home"))
        self.assertContains(response, "GIS")
        self.assertContains(response, "HR")
