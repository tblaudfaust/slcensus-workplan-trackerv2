from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.activities.models import Activity, Status
from apps.notifications.emailing import eligible_recipients, project_owner_recipients, send_notification
from apps.notifications.models import RuleType
from apps.projects.models import Project


class Command(BaseCommand):
    help = "Sends each active project's owner a weekly progress/overdue/upcoming/at-risk summary."

    def handle(self, *args, **options):
        today = timezone.localdate()
        week_end = today + timezone.timedelta(days=7)
        sent = 0

        for project in Project.objects.filter(is_active=True).select_related("owner", "co_owner"):
            activities = list(Activity.objects.filter(project=project).select_related("workstream"))
            if not activities:
                continue

            total = len(activities)
            completed = sum(1 for a in activities if a.status == Status.COMPLETED)
            readiness = round((completed / total) * 100) if total else 0
            overdue = sorted((a for a in activities if a.is_overdue), key=lambda a: a.end_date)
            at_risk = [a for a in activities if a.status == Status.AT_RISK]
            upcoming = sorted(
                (
                    a
                    for a in activities
                    if a.end_date and today <= a.end_date <= week_end and a.status != Status.COMPLETED
                ),
                key=lambda a: a.end_date,
            )
            workstream_rows = self._workstream_rows(project, activities)

            # Sent per-recipient (rather than one send_notification call
            # covering both) so the Owner and Co-Owner each get their own
            # name in the greeting instead of both seeing the Owner's.
            for recipient in eligible_recipients(*project_owner_recipients(project)):
                sent += send_notification(
                    rule_type=RuleType.WEEKLY_DIGEST,
                    template="weekly_digest",
                    subject=f"[Census Tracker] Weekly summary: {project.name}",
                    context={
                        "recipient_name": recipient.get_full_name() or recipient.username,
                        "project": project,
                        "readiness": readiness,
                        "overdue": overdue[:15],
                        "at_risk": at_risk[:15],
                        "upcoming": upcoming[:15],
                        "workstream_rows": workstream_rows,
                    },
                    recipients=[recipient],
                )

        self.stdout.write(self.style.SUCCESS(f"send_weekly_digest: sent {sent} email(s)."))

    def _workstream_rows(self, project, activities):
        from collections import defaultdict

        totals, completed = defaultdict(int), defaultdict(int)
        for a in activities:
            totals[a.workstream_id] += 1
            if a.status == Status.COMPLETED:
                completed[a.workstream_id] += 1
        rows = []
        for ws in project.workstreams.all():
            total = totals.get(ws.id, 0)
            done = completed.get(ws.id, 0)
            rows.append(
                {"workstream": ws, "total": total, "completed": done, "percent": round((done / total) * 100) if total else 0}
            )
        return rows
