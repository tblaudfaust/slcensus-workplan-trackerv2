from django.test import TestCase

from apps.activities.models import Activity
from apps.projects.models import Project, Workstream

from . import permissions
from .models import Role, User


class PermissionTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user("admin", password="x", role=Role.ADMIN)
        self.owner = User.objects.create_user("owner", password="x", role=Role.PROJECT_OWNER)
        self.other_owner = User.objects.create_user("owner2", password="x", role=Role.PROJECT_OWNER)
        self.ws_owner = User.objects.create_user("wsowner", password="x", role=Role.WORKSTREAM_OWNER)
        self.contributor = User.objects.create_user("contrib", password="x", role=Role.CONTRIBUTOR)
        self.viewer = User.objects.create_user("viewer", password="x", role=Role.VIEWER)

        self.project = Project.objects.create(name="Census", owner=self.owner)
        self.workstream = Workstream.objects.create(project=self.project, name="GIS")
        self.workstream.members.add(self.ws_owner)
        self.activity = Activity.objects.create(
            project=self.project, workstream=self.workstream, name="Task", responsible=self.contributor
        )

    def test_admin_can_edit_anything(self):
        self.assertTrue(permissions.can_edit_activity(self.admin, self.activity))

    def test_project_owner_can_edit_own_project_only(self):
        self.assertTrue(permissions.can_edit_activity(self.owner, self.activity))
        self.assertFalse(permissions.can_edit_activity(self.other_owner, self.activity))

    def test_workstream_owner_can_edit_own_workstream(self):
        self.assertTrue(permissions.can_edit_activity(self.ws_owner, self.activity))

    def test_workstream_owner_cannot_edit_other_workstream(self):
        other_ws = Workstream.objects.create(project=self.project, name="HR")
        other_activity = Activity.objects.create(project=self.project, workstream=other_ws, name="Other")
        self.assertFalse(permissions.can_edit_activity(self.ws_owner, other_activity))

    def test_contributor_can_edit_only_their_own_assigned_activity(self):
        self.assertTrue(permissions.can_edit_activity(self.contributor, self.activity))
        unassigned = Activity.objects.create(project=self.project, workstream=self.workstream, name="Unassigned")
        self.assertFalse(permissions.can_edit_activity(self.contributor, unassigned))

    def test_viewer_can_never_edit(self):
        self.assertFalse(permissions.can_edit_activity(self.viewer, self.activity))

    def test_only_admin_and_owning_project_owner_can_delete(self):
        self.assertTrue(permissions.can_delete_activity(self.admin, self.activity))
        self.assertTrue(permissions.can_delete_activity(self.owner, self.activity))
        self.assertFalse(permissions.can_delete_activity(self.ws_owner, self.activity))
        self.assertFalse(permissions.can_delete_activity(self.contributor, self.activity))

    def test_can_upload_workplans_excludes_contributor_and_viewer(self):
        self.assertTrue(permissions.can_upload_workplans(self.admin))
        self.assertTrue(permissions.can_upload_workplans(self.owner))
        self.assertTrue(permissions.can_upload_workplans(self.ws_owner))
        self.assertFalse(permissions.can_upload_workplans(self.contributor))
        self.assertFalse(permissions.can_upload_workplans(self.viewer))


class CoOwnerPermissionTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("owner", password="x", role=Role.PROJECT_OWNER)
        self.co_owner = User.objects.create_user("co_owner", password="x", role=Role.PROJECT_OWNER)
        self.other_owner = User.objects.create_user("other", password="x", role=Role.PROJECT_OWNER)
        self.project = Project.objects.create(name="Census", owner=self.owner, co_owner=self.co_owner)
        self.workstream = Workstream.objects.create(project=self.project, name="GIS")
        self.activity = Activity.objects.create(project=self.project, workstream=self.workstream, name="Task")

    def test_co_owner_has_same_rights_as_owner(self):
        self.assertTrue(permissions.can_manage_project(self.co_owner, self.project))
        self.assertTrue(permissions.can_edit_activity(self.co_owner, self.activity))
        self.assertTrue(permissions.can_delete_activity(self.co_owner, self.activity))
        self.assertTrue(permissions.can_validate_completion(self.co_owner, self.activity))

    def test_unrelated_project_owner_still_excluded(self):
        self.assertFalse(permissions.can_manage_project(self.other_owner, self.project))
        self.assertFalse(permissions.can_edit_activity(self.other_owner, self.activity))
