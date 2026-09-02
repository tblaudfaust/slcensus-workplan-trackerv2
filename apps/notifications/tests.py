import datetime

from django.core import mail
from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import Role, User
from apps.activities.models import Activity, Status
from apps.projects.models import Project, Workstream

from .apps import _seed_default_rules
from .emailing import already_sent_today, eligible_recipients, send_notification
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
