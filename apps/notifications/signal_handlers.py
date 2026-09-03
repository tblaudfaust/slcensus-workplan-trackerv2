from django.dispatch import receiver

from apps.activities.models import Status
from apps.activities.signals import activity_changed, activity_created

from .emailing import activity_owner_recipients, eligible_recipients, project_owner_recipients, rule_enabled, send_notification
from .models import RuleType


@receiver(activity_created)
def on_activity_created(sender, activity, changed_by=None, source="MANUAL", **kwargs):
    if not activity.responsible_id or not rule_enabled(RuleType.TASK_ASSIGNED):
        return
    recipients = eligible_recipients(activity.responsible)
    send_notification(
        rule_type=RuleType.TASK_ASSIGNED,
        template="task_assigned",
        subject=f"[Census Tracker] You've been assigned: {activity.name}",
        context={"activity": activity, "recipient_name": activity.responsible.get_full_name() or activity.responsible.username},
        recipients=recipients,
        activity=activity,
    )


@receiver(activity_changed)
def on_activity_changed(sender, activity, changed_fields, changed_by=None, source="MANUAL", **kwargs):
    if "responsible_id" in changed_fields and activity.responsible_id and rule_enabled(RuleType.TASK_ASSIGNED):
        send_notification(
            rule_type=RuleType.TASK_ASSIGNED,
            template="task_assigned",
            subject=f"[Census Tracker] You've been assigned: {activity.name}",
            context={"activity": activity, "recipient_name": activity.responsible.get_full_name() or activity.responsible.username},
            recipients=eligible_recipients(activity.responsible),
            activity=activity,
        )

    if "status" in changed_fields:
        old_status_display, new_status_display = changed_fields["status"]
        if rule_enabled(RuleType.STATUS_CHANGE):
            recipients = eligible_recipients(*activity_owner_recipients(activity), *project_owner_recipients(activity.project))
            for user in recipients:
                send_notification(
                    rule_type=RuleType.STATUS_CHANGE,
                    template="status_changed",
                    subject=f"[Census Tracker] Status changed: {activity.name}",
                    context={
                        "activity": activity,
                        "recipient_name": user.get_full_name() or user.username,
                        "old_status": old_status_display,
                        "new_status": new_status_display,
                    },
                    recipients=[user],
                    activity=activity,
                )

        if activity.status == Status.AT_RISK and rule_enabled(RuleType.AT_RISK):
            recipients = eligible_recipients(
                *activity_owner_recipients(activity), *project_owner_recipients(activity.project), activity.workstream.lead
            )
            send_notification(
                rule_type=RuleType.AT_RISK,
                template="at_risk",
                subject=f"[Census Tracker] AT RISK: {activity.name}",
                context={"activity": activity, "recipient_name": "team"},
                recipients=recipients,
                activity=activity,
            )

        if activity.status == Status.PENDING_VALIDATION and rule_enabled(RuleType.VALIDATION_REQUESTED):
            recipients = eligible_recipients(activity.workstream.lead, activity.workstream.backup_lead)
            send_notification(
                rule_type=RuleType.VALIDATION_REQUESTED,
                template="validation_requested",
                subject=f"[Census Tracker] Ready for validation: {activity.name}",
                context={"activity": activity, "recipient_name": "team"},
                recipients=recipients,
                activity=activity,
            )

        if (
            activity.status == Status.COMPLETED
            and activity.is_milestone
            and rule_enabled(RuleType.MILESTONE_COMPLETED)
        ):
            recipients = eligible_recipients(*project_owner_recipients(activity.project), activity.workstream.lead)
            send_notification(
                rule_type=RuleType.MILESTONE_COMPLETED,
                template="milestone_completed",
                subject=f"[Census Tracker] Milestone completed: {activity.name}",
                context={"activity": activity, "recipient_name": "team"},
                recipients=recipients,
                activity=activity,
            )
