from collections import defaultdict

from django.core.management.base import BaseCommand
from django.db.models import Q
from django.utils import timezone

from apps.activities.models import Activity, Status
from apps.notifications.emailing import already_sent_today, eligible_recipients, project_owner_recipients, send_notification
from apps.notifications.models import NotificationLog, NotificationRule, RuleType


class Command(BaseCommand):
    help = "Sends deadline-reminder, overdue, and workstream-overdue-threshold emails for open activities."

    def handle(self, *args, **options):
        today = timezone.localdate()
        sent = 0
        sent += self._send_deadline_reminders(today)
        sent += self._send_overdue_alerts(today)
        sent += self._send_workstream_overdue_alerts(today)
        self.stdout.write(self.style.SUCCESS(f"check_deadlines: sent {sent} email(s)."))

    def _send_deadline_reminders(self, today):
        count = 0
        rules = NotificationRule.objects.filter(rule_type=RuleType.DEADLINE_REMINDER, enabled=True)
        for rule in rules:
            if rule.days_before is None:
                continue
            target_date = today + timezone.timedelta(days=rule.days_before)
            activities = Activity.objects.filter(
                end_date=target_date, status__in=Status.open_statuses()
            ).select_related("responsible", "project", "workstream")
            for activity in activities:
                if already_sent_today(RuleType.DEADLINE_REMINDER, activity):
                    continue
                recipients = eligible_recipients(activity.responsible)
                if not recipients:
                    continue
                count += send_notification(
                    rule_type=RuleType.DEADLINE_REMINDER,
                    template="deadline_reminder",
                    subject=f"[Census Tracker] Due in {rule.days_before} day(s): {activity.name}",
                    context={
                        "activity": activity,
                        "recipient_name": activity.responsible.get_full_name() or activity.responsible.username,
                        "days_before": rule.days_before,
                    },
                    recipients=recipients,
                    activity=activity,
                )
        return count

    def _send_overdue_alerts(self, today):
        count = 0
        if not NotificationRule.objects.filter(rule_type=RuleType.OVERDUE, enabled=True).exists():
            return 0
        activities = Activity.objects.filter(
            end_date__lt=today, status__in=Status.open_statuses()
        ).select_related("responsible", "project", "workstream")
        for activity in activities:
            if already_sent_today(RuleType.OVERDUE, activity):
                continue
            recipients = eligible_recipients(activity.responsible, *project_owner_recipients(activity.project))
            if not recipients:
                continue
            count += send_notification(
                rule_type=RuleType.OVERDUE,
                template="overdue",
                subject=f"[Census Tracker] OVERDUE: {activity.name}",
                context={"activity": activity, "recipient_name": "team"},
                recipients=recipients,
                activity=activity,
            )
        return count

    def _send_workstream_overdue_alerts(self, today):
        rule = NotificationRule.objects.filter(rule_type=RuleType.WORKSTREAM_OVERDUE, enabled=True).first()
        if not rule or not rule.threshold:
            return 0

        overdue_by_workstream = defaultdict(list)
        activities = Activity.objects.filter(
            end_date__lt=today, status__in=Status.open_statuses()
        ).select_related("workstream", "workstream__lead", "project", "project__owner", "project__co_owner")
        for activity in activities:
            overdue_by_workstream[activity.workstream].append(activity)

        count = 0
        for workstream, overdue_activities in overdue_by_workstream.items():
            if len(overdue_activities) < rule.threshold:
                continue
            already_sent = NotificationLog.objects.filter(
                rule_type=RuleType.WORKSTREAM_OVERDUE, workstream=workstream, sent_at__date=today, status="SENT"
            ).exists()
            if already_sent:
                continue
            recipients = eligible_recipients(*project_owner_recipients(workstream.project), workstream.lead)
            if not recipients:
                continue
            count += send_notification(
                rule_type=RuleType.WORKSTREAM_OVERDUE,
                template="workstream_overdue",
                subject=f"[Census Tracker] {workstream.name}: {len(overdue_activities)} overdue activities",
                context={
                    "recipient_name": "team",
                    "workstream": workstream,
                    "overdue_count": len(overdue_activities),
                    "overdue_activities": overdue_activities[:20],
                    "threshold": rule.threshold,
                },
                recipients=recipients,
                workstream=workstream,
            )
        return count
