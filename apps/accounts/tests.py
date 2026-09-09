import re

from django.core import mail
from django.test import TestCase
from django.urls import reverse

from apps.activities.models import Activity
from apps.projects.models import Project, Workstream

from . import permissions
from .models import Role, User


def _extract_reset_path(test_case, email_body):
    match = re.search(r"(/accounts/reset/\S+/\S+/)", email_body)
    test_case.assertIsNotNone(match, f"No reset link found in email body:\n{email_body}")
    return match.group(1)


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


class PasswordResetFlowTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("alex", password="old-password-123", email="alex@example.org")

    def test_request_for_known_email_sends_a_working_reset_link(self):
        response = self.client.post(reverse("accounts:password_reset"), {"email": "alex@example.org"})
        self.assertRedirects(response, reverse("accounts:password_reset_done"))
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("alex@example.org", mail.outbox[0].to)
        self.assertIn("Password reset", mail.outbox[0].subject)

        reset_path = _extract_reset_path(self, mail.outbox[0].body)
        # Following the emailed link redirects (uidb64/token get consumed
        # into the session) to the same view with a stable "set-password"
        # placeholder in the URL -- the real Django auth flow.
        follow_response = self.client.get(reset_path, follow=True)
        self.assertEqual(follow_response.status_code, 200)
        self.assertTrue(follow_response.context["validlink"])

        set_password_url = follow_response.request["PATH_INFO"]
        confirm_response = self.client.post(
            set_password_url, {"new_password1": "brand-new-password-456", "new_password2": "brand-new-password-456"}
        )
        self.assertRedirects(confirm_response, reverse("accounts:password_reset_complete"))

        self.assertFalse(self.client.login(username="alex", password="old-password-123"))
        self.assertTrue(self.client.login(username="alex", password="brand-new-password-456"))

    def test_request_for_unknown_email_sends_nothing_but_still_succeeds(self):
        # Must not reveal whether an email is registered -- same redirect,
        # no email sent.
        response = self.client.post(reverse("accounts:password_reset"), {"email": "nobody@example.org"})
        self.assertRedirects(response, reverse("accounts:password_reset_done"))
        self.assertEqual(len(mail.outbox), 0)

    def test_mismatched_new_passwords_are_rejected(self):
        self.client.post(reverse("accounts:password_reset"), {"email": "alex@example.org"})
        reset_path = _extract_reset_path(self, mail.outbox[0].body)
        follow_response = self.client.get(reset_path, follow=True)
        set_password_url = follow_response.request["PATH_INFO"]

        confirm_response = self.client.post(
            set_password_url, {"new_password1": "brand-new-password-456", "new_password2": "does-not-match"}
        )
        self.assertEqual(confirm_response.status_code, 200)
        self.assertTrue(self.client.login(username="alex", password="old-password-123"))


class UserInviteFlowTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user("admin", password="pass12345", role=Role.ADMIN)
        self.client.login(username="admin", password="pass12345")

    def test_creating_a_user_with_email_sends_a_working_set_password_link(self):
        response = self.client.post(
            reverse("accounts:user_create"),
            {
                "username": "newperson",
                "first_name": "New",
                "last_name": "Person",
                "email": "new.person@example.org",
                "role": Role.CONTRIBUTOR,
                "phone": "",
            },
        )
        self.assertRedirects(response, reverse("accounts:user_list"))

        created = User.objects.get(username="newperson")
        self.assertFalse(created.has_usable_password())

        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("new.person@example.org", mail.outbox[0].to)
        self.assertIn("newperson", mail.outbox[0].body)  # username is spelled out in the email

        reset_path = _extract_reset_path(self, mail.outbox[0].body)
        follow_response = self.client.get(reset_path, follow=True)
        self.assertTrue(follow_response.context["validlink"])
        set_password_url = follow_response.request["PATH_INFO"]
        self.client.post(
            set_password_url, {"new_password1": "their-own-password-789", "new_password2": "their-own-password-789"}
        )
        self.assertTrue(self.client.login(username="newperson", password="their-own-password-789"))

    def test_creating_a_user_without_email_sends_nothing_and_warns(self):
        response = self.client.post(
            reverse("accounts:user_create"),
            {
                "username": "noemail",
                "first_name": "",
                "last_name": "",
                "email": "",
                "role": Role.CONTRIBUTOR,
                "phone": "",
            },
        )
        self.assertRedirects(response, reverse("accounts:user_list"))
        self.assertEqual(len(mail.outbox), 0)
        created = User.objects.get(username="noemail")
        self.assertFalse(created.has_usable_password())

    def test_non_admin_cannot_create_users(self):
        self.client.logout()
        User.objects.create_user("plain", password="x", role=Role.VIEWER)
        self.client.login(username="plain", password="x")
        response = self.client.post(
            reverse("accounts:user_create"),
            {"username": "blocked", "email": "blocked@example.org", "role": Role.VIEWER},
        )
        self.assertNotEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username="blocked").exists())

    def test_resend_invite_from_user_list(self):
        target = User.objects.create_user("existing", password="x", email="existing@example.org")
        target.set_unusable_password()
        target.save()

        response = self.client.post(reverse("accounts:user_send_invite", args=[target.pk]))
        self.assertRedirects(response, reverse("accounts:user_list"))
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("existing@example.org", mail.outbox[0].to)

    def test_resend_invite_without_email_shows_error_not_crash(self):
        target = User.objects.create_user("noemailuser", password="x")
        response = self.client.post(reverse("accounts:user_send_invite", args=[target.pk]))
        self.assertRedirects(response, reverse("accounts:user_list"))
        self.assertEqual(len(mail.outbox), 0)

    def test_non_admin_cannot_send_invites(self):
        self.client.logout()
        plain = User.objects.create_user("plain2", password="x", role=Role.VIEWER)
        target = User.objects.create_user("target", password="x", email="target@example.org")
        self.client.login(username="plain2", password="x")
        response = self.client.post(reverse("accounts:user_send_invite", args=[target.pk]))
        self.assertNotEqual(response.status_code, 200)
        self.assertEqual(len(mail.outbox), 0)
