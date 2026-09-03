import datetime

from django.core import mail
from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import Role, User
from apps.activities.models import Activity, Status
from apps.projects.models import Project, Workstream

from .apps import _seed_default_rules
from .emailing import (
    activity_owner_recipients,
    already_sent_today,
    eligible_recipients,
    project_owner_recipients,
    send_notification,
)
from .models import NotificationLog, NotificationRule, RuleType


class DefaultRuleSeedingTests(TestCase):
    def test_seeding_creates_one_row_per_reminder_window_plus_other_types(self):
        _seed_default_rules(sender=None)
        self.assertEqual(
            NotificationRule.objects.filter(rule_type=RuleType.DEADLINE_REMINDER).count(), 4
        )
        self.assertTrue(NotificationRule.objects.filter(rule_type=RuleType.OVERDUE, enabled=True).exists())

    def test_seeding_is_idempotent(self):
        _seed_default_rules(sender=None)
        NotificationRule.objects.filter(rule_type=RuleType.OVERDUE).update(enabled=False)
        _seed_default_rules(sender=None)
        # A second call must not resurrect the admin's change.
        self.assertFalse(NotificationRule.objects.get(rule_type=RuleType.OVERDUE).enabled)


class EligibleRecipientsTests(TestCase):
    def test_filters_out_users_without_email_and_opted_out(self):
        with_email = User.objects.create_user("a", password="x", email="a@example.org")
        no_email = User.objects.create_user("b", password="x", email="")
        opted_out = User.objects.create_user(
            "c", password="x", email="c@example.org", receive_email_notifications=False
        )
        result = eligible_recipients(with_email, no_email, opted_out, None)
        self.assertEqual(result, [with_email])

    def test_deduplicates_same_user_passed_twice(self):
        user = User.objects.create_user("a", password="x", email="a@example.org")
        result = eligible_recipients(user, user)
        self.assertEqual(result, [user])


class ActivityOwnerRecipientsTests(TestCase):
    def setUp(self):
        owner = User.objects.create_user("owner", password="x", role=Role.PROJECT_OWNER)
        self.project = Project.objects.create(name="Census", owner=owner)
        self.lead = User.objects.create_user("lead", password="x", role=Role.WORKSTREAM_OWNER)
        self.backup = User.objects.create_user("backup", password="x", role=Role.WORKSTREAM_OWNER)
        self.person = User.objects.create_user("person", password="x", role=Role.CONTRIBUTOR)
        self.workstream = Workstream.objects.create(
            project=self.project, name="GIS", lead=self.lead, backup_lead=self.backup
        )

    def test_prefers_matched_responsible_user(self):
        activity = Activity.objects.create(
            project=self.project, workstream=self.workstream, name="Task",
            responsible=self.person, responsible_text="ignored role title",
        )
        self.assertEqual(activity_owner_recipients(activity), [self.person])

    def test_falls_back_to_lead_and_backup_when_only_free_text(self):
        activity = Activity.objects.create(
            project=self.project, workstream=self.workstream, name="Task", responsible_text="GIS LEAD"
        )
        self.assertEqual(activity_owner_recipients(activity), [self.lead, self.backup])

    def test_empty_when_no_owner_and_no_lead(self):
        bare_ws = Workstream.objects.create(project=self.project, name="Publicity")
        activity = Activity.objects.create(project=self.project, workstream=bare_ws, name="Task")
        self.assertEqual(activity_owner_recipients(activity), [])


class ProjectOwnerRecipientsTests(TestCase):
    def test_includes_both_owner_and_co_owner(self):
        owner = User.objects.create_user("owner", password="x", role=Role.PROJECT_OWNER)
        co_owner = User.objects.create_user("co_owner", password="x", role=Role.PROJECT_OWNER)
        project = Project.objects.create(name="Census", owner=owner, co_owner=co_owner)
        self.assertEqual(project_owner_recipients(project), [owner, co_owner])

    def test_omits_unset_co_owner(self):
        owner = User.objects.create_user("owner", password="x", role=Role.PROJECT_OWNER)
        project = Project.objects.create(name="Census", owner=owner)
        self.assertEqual(project_owner_recipients(project), [owner])


class SendNotificationTests(TestCase):
    def setUp(self):
        owner = User.objects.create_user("owner", password="x", role=Role.PROJECT_OWNER, email="owner@example.org")
        self.project = Project.objects.create(name="Census", owner=owner)
        self.ws = Workstream.objects.create(project=self.project, name="GIS")
        self.activity = Activity.objects.create(project=self.project, workstream=self.ws, name="Task")
        self.recipient = User.objects.create_user("r", password="x", email="r@example.org")

    def test_sends_email_and_logs_success(self):
        sent = send_notification(
            rule_type=RuleType.TASK_ASSIGNED,
            template="task_assigned",
            subject="Test subject",
            context={"activity": self.activity, "recipient_name": "R"},
            recipients=[self.recipient],
            activity=self.activity,
        )
        self.assertEqual(sent, 1)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["r@example.org"])
        log = NotificationLog.objects.get()
        self.assertEqual(log.status, "SENT")

    def test_already_sent_today_detects_duplicate(self):
        send_notification(
            rule_type=RuleType.OVERDUE,
            template="overdue",
            subject="Test",
            context={"activity": self.activity, "recipient_name": "R"},
            recipients=[self.recipient],
            activity=self.activity,
        )
        self.assertTrue(already_sent_today(RuleType.OVERDUE, self.activity))
        self.assertFalse(already_sent_today(RuleType.TASK_ASSIGNED, self.activity))


class CheckDeadlinesCommandTests(TestCase):
    def setUp(self):
        _seed_default_rules(sender=None)
        self.owner = User.objects.create_user("owner", password="x", role=Role.PROJECT_OWNER, email="owner@example.org")
        self.project = Project.objects.create(name="Census", owner=self.owner)
        self.ws = Workstream.objects.create(project=self.project, name="GIS")
        self.responsible = User.objects.create_user("r", password="x", email="r@example.org")

    def test_deadline_reminder_sent_for_activity_due_in_window(self):
        from django.core.management import call_command

        Activity.objects.create(
            project=self.project,
            workstream=self.ws,
            name="Due soon",
            end_date=timezone.localdate() + datetime.timedelta(days=3),
            status=Status.ONGOING,
            responsible=self.responsible,
        )
        call_command("check_deadlines")
        self.assertTrue(
            NotificationLog.objects.filter(rule_type=RuleType.DEADLINE_REMINDER, recipient_email="r@example.org").exists()
        )

    def test_overdue_alert_sent_for_past_due_activity(self):
        from django.core.management import call_command

        Activity.objects.create(
            project=self.project,
            workstream=self.ws,
            name="Overdue task",
            end_date=timezone.localdate() - datetime.timedelta(days=2),
            status=Status.ONGOING,
            responsible=self.responsible,
        )
        call_command("check_deadlines")
        self.assertTrue(NotificationLog.objects.filter(rule_type=RuleType.OVERDUE).exists())

    def test_workstream_overdue_alert_fires_at_threshold(self):
        from django.core.management import call_command

        rule = NotificationRule.objects.get(rule_type=RuleType.WORKSTREAM_OVERDUE)
        rule.threshold = 2
        rule.save()
        for i in range(2):
            Activity.objects.create(
                project=self.project,
                workstream=self.ws,
                name=f"Overdue {i}",
                end_date=timezone.localdate() - datetime.timedelta(days=2),
                status=Status.ONGOING,
            )
        call_command("check_deadlines")
        self.assertTrue(NotificationLog.objects.filter(rule_type=RuleType.WORKSTREAM_OVERDUE).exists())


class ValidationNotificationTests(TestCase):
    def setUp(self):
        _seed_default_rules(sender=None)
        self.owner = User.objects.create_user(
            "owner", password="x", role=Role.PROJECT_OWNER, email="owner@example.org"
        )
        self.lead = User.objects.create_user(
            "lead", password="pass12345", role=Role.WORKSTREAM_OWNER, email="lead@example.org"
        )
        self.project = Project.objects.create(name="Census", owner=self.owner)
        self.ws = Workstream.objects.create(project=self.project, name="GIS", lead=self.lead)
        self.activity = Activity.objects.create(
            project=self.project, workstream=self.ws, name="Task", status=Status.PENDING_VALIDATION
        )

    def test_marking_pending_validation_notifies_the_lead(self):
        from django.urls import reverse

        admin = User.objects.create_user("admin", password="pass12345", role=Role.ADMIN)
        self.activity.status = Status.ONGOING
        self.activity.save()
        self.client.login(username="admin", password="pass12345")
        self.client.post(
            reverse("activities:edit", args=[self.activity.pk]),
            {
                "workstream": self.ws.pk,
                "name": self.activity.name,
                "status": Status.PENDING_VALIDATION,
                "progress_percent": 90,
                "responsible_text": "",
            },
        )
        self.assertTrue(
            NotificationLog.objects.filter(rule_type=RuleType.VALIDATION_REQUESTED, recipient_email="lead@example.org").exists()
        )

    def test_validating_notifies_the_project_owner(self):
        from django.urls import reverse

        self.client.login(username="lead", password="pass12345")
        self.client.post(reverse("activities:validate", args=[self.activity.pk]))
        self.assertTrue(
            NotificationLog.objects.filter(
                rule_type=RuleType.COMPLETION_VALIDATED, recipient_email="owner@example.org"
            ).exists()
        )

    def test_validating_notifies_the_co_owner_too(self):
        from django.urls import reverse

        co_owner = User.objects.create_user(
            "co_owner", password="x", role=Role.PROJECT_OWNER, email="co-owner@example.org"
        )
        self.project.co_owner = co_owner
        self.project.save()

        self.client.login(username="lead", password="pass12345")
        self.client.post(reverse("activities:validate", args=[self.activity.pk]))
        self.assertTrue(
            NotificationLog.objects.filter(
                rule_type=RuleType.COMPLETION_VALIDATED, recipient_email="co-owner@example.org"
            ).exists()
        )


class WeeklyDigestCoOwnerTests(TestCase):
    def test_digest_sent_to_both_owner_and_co_owner(self):
        from django.core.management import call_command

        owner = User.objects.create_user("owner", password="x", role=Role.PROJECT_OWNER, email="owner@example.org")
        co_owner = User.objects.create_user(
            "co_owner", password="x", role=Role.PROJECT_OWNER, email="co-owner@example.org"
        )
        project = Project.objects.create(name="Census", owner=owner, co_owner=co_owner)
        ws = Workstream.objects.create(project=project, name="GIS")
        Activity.objects.create(project=project, workstream=ws, name="Task", status=Status.ONGOING)

        call_command("send_weekly_digest")

        self.assertTrue(NotificationLog.objects.filter(recipient_email="owner@example.org").exists())
        self.assertTrue(NotificationLog.objects.filter(recipient_email="co-owner@example.org").exists())
