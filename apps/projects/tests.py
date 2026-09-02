from django.test import TestCase

from apps.accounts.models import Role, User
from apps.activities.models import Activity, Status

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
