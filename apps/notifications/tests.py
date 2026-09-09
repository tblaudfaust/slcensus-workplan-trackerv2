import datetime
from unittest.mock import Mock, patch

from django.core import mail
from django.test import TestCase, override_settings
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
from .sms import SmsSendError, normalize_phone, send_sms


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


class NormalizePhoneTests(TestCase):
    def test_already_prefixed_with_country_code(self):
        self.assertEqual(normalize_phone("23230123456"), "23230123456")

    def test_leading_plus_is_stripped(self):
        self.assertEqual(normalize_phone("+23230123456"), "23230123456")

    def test_local_eight_digit_form_gets_country_code(self):
        self.assertEqual(normalize_phone("30123456"), "23230123456")

    def test_local_nine_digit_form_with_leading_zero(self):
        self.assertEqual(normalize_phone("030123456"), "23230123456")

    def test_formatting_characters_are_stripped(self):
        self.assertEqual(normalize_phone("+232 30-123-456"), "23230123456")

    def test_blank_or_missing_returns_none(self):
        self.assertIsNone(normalize_phone(""))
        self.assertIsNone(normalize_phone(None))


@override_settings(
    SMS_ENABLED=True,
    SMS_API_BASE_URL="https://api.sierrahive.com",
    SMS_CLIENT_ID="111",
    SMS_CLIENT_SECRET="222",
    SMS_TOKEN="333",
    SMS_SENDER_ID="SLCensus",
)
class SendSmsTests(TestCase):
    def test_disabled_raises_without_any_network_call(self):
        with override_settings(SMS_ENABLED=False):
            with patch("apps.notifications.sms.requests.post") as mock_post:
                with self.assertRaises(SmsSendError):
                    send_sms("23230123456", "hello")
                mock_post.assert_not_called()

    def test_invalid_phone_raises_without_any_network_call(self):
        with patch("apps.notifications.sms.requests.post") as mock_post:
            with self.assertRaises(SmsSendError):
                send_sms("", "hello")
            mock_post.assert_not_called()

    @patch("apps.notifications.sms.requests.post")
    def test_success_sends_expected_payload_and_auth(self, mock_post):
        mock_response = Mock()
        mock_response.json.return_value = {"Status": "pending", "Ticket": "abc-123"}
        mock_post.return_value = mock_response

        result = send_sms("030123456", "You're assigned a task", reference="ref-1")

        self.assertEqual(result["Status"], "pending")
        mock_response.raise_for_status.assert_called_once()
        args, kwargs = mock_post.call_args
        self.assertEqual(args[0], "https://api.sierrahive.com/v1/messages/sms")
        self.assertEqual(
            kwargs["json"],
            {"From": "SLCensus", "To": "23230123456", "Content": "You're assigned a task", "Reference": "ref-1"},
        )
        self.assertEqual(kwargs["headers"]["X-Wallet"], "Token 333")
        self.assertTrue(kwargs["headers"]["Authorization"].startswith("Basic "))

    @patch("apps.notifications.sms.requests.post")
    def test_http_failure_raises_sms_send_error(self, mock_post):
        import requests

        mock_post.side_effect = requests.ConnectionError("network down")
        with self.assertRaises(SmsSendError):
            send_sms("23230123456", "hello")


class ActivitySignalUploadSourceTests(TestCase):
    """A bulk upload can create/update hundreds of activities in one
    request; sending a real-time email per row (as happens for
    source="MANUAL") is both unwanted (nobody wants 100+ "assigned"
    emails for a spreadsheet import) and, since each send is a blocking
    SMTP round-trip, can push the request past the server's timeout."""

    def setUp(self):
        _seed_default_rules(sender=None)
        owner = User.objects.create_user("owner", password="x", role=Role.PROJECT_OWNER, email="owner@example.org")
        self.project = Project.objects.create(name="Census", owner=owner)
        self.ws = Workstream.objects.create(project=self.project, name="GIS")
        self.responsible = User.objects.create_user("r", password="x", email="r@example.org")

    def test_activity_created_from_upload_sends_no_email(self):
        from apps.activities.signals import activity_created

        activity = Activity.objects.create(
            project=self.project, workstream=self.ws, name="Task", responsible=self.responsible
        )
        activity_created.send(sender=Activity, activity=activity, changed_by=None, source="UPLOAD")
        self.assertEqual(len(mail.outbox), 0)

    def test_activity_created_from_manual_still_sends_email(self):
        from apps.activities.signals import activity_created

        activity = Activity.objects.create(
            project=self.project, workstream=self.ws, name="Task", responsible=self.responsible
        )
        activity_created.send(sender=Activity, activity=activity, changed_by=None, source="MANUAL")
        self.assertEqual(len(mail.outbox), 1)

    def test_activity_changed_from_upload_sends_no_email(self):
        from apps.activities.signals import activity_changed

        activity = Activity.objects.create(
            project=self.project, workstream=self.ws, name="Task", status=Status.NOT_STARTED
        )
        activity_changed.send(
            sender=Activity,
            activity=activity,
            changed_fields={"status": ("Not Started", "Ongoing")},
            changed_by=None,
            source="UPLOAD",
        )
        self.assertEqual(len(mail.outbox), 0)


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
            NotificationLog.objects.filter(rule_type=RuleType.DEADLINE_REMINDER, recipient="r@example.org").exists()
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

    @override_settings(SMS_ENABLED=True, SMS_CLIENT_ID="1", SMS_CLIENT_SECRET="2", SMS_TOKEN="3")
    @patch("apps.notifications.sms.requests.post")
    def test_overdue_alert_also_sends_sms_to_opted_in_recipient(self, mock_post):
        mock_post.return_value = Mock(json=lambda: {"Status": "pending"})
        self.responsible.phone = "23230123456"
        self.responsible.receive_sms_notifications = True
        self.responsible.save()
        Activity.objects.create(
            project=self.project,
            workstream=self.ws,
            name="Overdue task",
            end_date=timezone.localdate() - datetime.timedelta(days=2),
            status=Status.ONGOING,
            responsible=self.responsible,
        )
        from django.core.management import call_command

        call_command("check_deadlines")
        self.assertTrue(
            NotificationLog.objects.filter(
                rule_type=RuleType.OVERDUE, channel="SMS", recipient="23230123456"
            ).exists()
        )
        mock_post.assert_called_once()

    @patch("apps.notifications.sms.requests.post")
    def test_overdue_alert_skips_sms_for_recipient_not_opted_in(self, mock_post):
        # self.responsible has no phone and receive_sms_notifications
        # defaults to False -- SMS must never be attempted for them.
        Activity.objects.create(
            project=self.project,
            workstream=self.ws,
            name="Overdue task",
            end_date=timezone.localdate() - datetime.timedelta(days=2),
            status=Status.ONGOING,
            responsible=self.responsible,
        )
        from django.core.management import call_command

        call_command("check_deadlines")
        self.assertFalse(NotificationLog.objects.filter(rule_type=RuleType.OVERDUE, channel="SMS").exists())
        mock_post.assert_not_called()

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


class AtRiskAlertSmsTests(TestCase):
    def setUp(self):
        _seed_default_rules(sender=None)
        owner = User.objects.create_user("owner", password="x", role=Role.PROJECT_OWNER, email="owner@example.org")
        self.project = Project.objects.create(name="Census", owner=owner)
        self.ws = Workstream.objects.create(project=self.project, name="GIS")
        self.responsible = User.objects.create_user(
            "r", password="x", email="r@example.org", phone="23230123456", receive_sms_notifications=True
        )
        self.activity = Activity.objects.create(
            project=self.project, workstream=self.ws, name="Task", status=Status.NOT_STARTED, responsible=self.responsible
        )

    @override_settings(SMS_ENABLED=True, SMS_CLIENT_ID="1", SMS_CLIENT_SECRET="2", SMS_TOKEN="3")
    @patch("apps.notifications.sms.requests.post")
    def test_marking_at_risk_sends_sms_to_opted_in_owner(self, mock_post):
        from apps.activities.signals import activity_changed

        mock_post.return_value = Mock(json=lambda: {"Status": "pending"})
        self.activity.status = Status.AT_RISK
        self.activity.save()
        activity_changed.send(
            sender=Activity,
            activity=self.activity,
            changed_fields={"status": ("Not Started", "At Risk")},
            changed_by=None,
            source="MANUAL",
        )
        self.assertTrue(
            NotificationLog.objects.filter(
                rule_type=RuleType.AT_RISK, channel="SMS", recipient="23230123456"
            ).exists()
        )
        mock_post.assert_called_once()

    @patch("apps.notifications.sms.requests.post")
    def test_status_change_that_is_not_at_risk_sends_no_sms(self, mock_post):
        from apps.activities.signals import activity_changed

        self.activity.status = Status.ONGOING
        self.activity.save()
        activity_changed.send(
            sender=Activity,
            activity=self.activity,
            changed_fields={"status": ("Not Started", "Ongoing")},
            changed_by=None,
            source="MANUAL",
        )
        self.assertFalse(NotificationLog.objects.filter(channel="SMS").exists())
        mock_post.assert_not_called()


class BroadcastViewTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user("admin", password="pass12345", role=Role.ADMIN)
        self.emailed = User.objects.create_user("a", password="x", email="a@example.org")
        self.opted_out = User.objects.create_user(
            "b", password="x", email="b@example.org", receive_email_notifications=False
        )
        self.sms_opted_in = User.objects.create_user(
            "c", password="x", email="c@example.org", phone="23230123456", receive_sms_notifications=True
        )
        self.inactive = User.objects.create_user("d", password="x", email="d@example.org", is_active=False)

    def test_non_admin_cannot_send_a_broadcast(self):
        from django.urls import reverse

        self.client.login(username="a", password="x")
        response = self.client.post(
            reverse("notifications:broadcast"), {"subject": "Hi", "message": "Body", "via_email": "on"}
        )
        self.assertNotEqual(response.status_code, 200)
        self.assertEqual(NotificationLog.objects.count(), 0)

    def test_email_broadcast_reaches_opted_in_active_users_only(self):
        from django.urls import reverse

        self.client.login(username="admin", password="pass12345")
        self.client.post(
            reverse("notifications:broadcast"),
            {"subject": "Heads up", "message": "New deadline next week", "via_email": "on"},
        )
        sent_to = set(
            NotificationLog.objects.filter(rule_type=RuleType.BROADCAST, channel="EMAIL").values_list(
                "recipient", flat=True
            )
        )
        self.assertEqual(sent_to, {"a@example.org", "c@example.org"})
        self.assertEqual(len(mail.outbox), 2)
        self.assertIn("Heads up", mail.outbox[0].subject)

    @override_settings(SMS_ENABLED=True, SMS_CLIENT_ID="1", SMS_CLIENT_SECRET="2", SMS_TOKEN="3")
    @patch("apps.notifications.sms.requests.post")
    def test_sms_broadcast_reaches_only_sms_opted_in_users(self, mock_post):
        from django.urls import reverse

        mock_post.return_value = Mock(json=lambda: {"Status": "pending"})
        self.client.login(username="admin", password="pass12345")
        self.client.post(
            reverse("notifications:broadcast"),
            {"subject": "Heads up", "message": "New deadline next week", "via_sms": "on"},
        )
        self.assertTrue(
            NotificationLog.objects.filter(
                rule_type=RuleType.BROADCAST, channel="SMS", recipient="23230123456"
            ).exists()
        )
        self.assertEqual(NotificationLog.objects.filter(rule_type=RuleType.BROADCAST, channel="SMS").count(), 1)
        mock_post.assert_called_once()

    def test_requires_at_least_one_channel(self):
        from django.urls import reverse

        self.client.login(username="admin", password="pass12345")
        self.client.post(reverse("notifications:broadcast"), {"subject": "Hi", "message": "Body"})
        self.assertEqual(NotificationLog.objects.count(), 0)
        self.assertEqual(len(mail.outbox), 0)

    def test_requires_subject_and_message(self):
        from django.urls import reverse

        self.client.login(username="admin", password="pass12345")
        self.client.post(reverse("notifications:broadcast"), {"subject": "", "message": "", "via_email": "on"})
        self.assertEqual(NotificationLog.objects.count(), 0)


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
            NotificationLog.objects.filter(rule_type=RuleType.VALIDATION_REQUESTED, recipient="lead@example.org").exists()
        )

    def test_validating_notifies_the_project_owner(self):
        from django.urls import reverse

        self.client.login(username="lead", password="pass12345")
        self.client.post(reverse("activities:validate", args=[self.activity.pk]))
        self.assertTrue(
            NotificationLog.objects.filter(
                rule_type=RuleType.COMPLETION_VALIDATED, recipient="owner@example.org"
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
                rule_type=RuleType.COMPLETION_VALIDATED, recipient="co-owner@example.org"
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

        self.assertTrue(NotificationLog.objects.filter(recipient="owner@example.org").exists())
        self.assertTrue(NotificationLog.objects.filter(recipient="co-owner@example.org").exists())
