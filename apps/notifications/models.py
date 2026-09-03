from django.conf import settings
from django.db import models


class RuleType(models.TextChoices):
    DEADLINE_REMINDER = "DEADLINE_REMINDER", "Deadline reminder"
    OVERDUE = "OVERDUE", "Activity overdue"
    AT_RISK = "AT_RISK", "Activity marked at risk"
    STATUS_CHANGE = "STATUS_CHANGE", "Activity status changed"
    TASK_ASSIGNED = "TASK_ASSIGNED", "Task assigned to owner"
    MILESTONE_COMPLETED = "MILESTONE_COMPLETED", "Major milestone completed"
    WORKSTREAM_OVERDUE = "WORKSTREAM_OVERDUE", "Workstream has several overdue activities"
    WEEKLY_DIGEST = "WEEKLY_DIGEST", "Weekly summary digest"
    VALIDATION_REQUESTED = "VALIDATION_REQUESTED", "Activity ready for validation"
    COMPLETION_VALIDATED = "COMPLETION_VALIDATED", "Completion validated by workstream owner"
    MANUAL_ALERT = "MANUAL_ALERT", "Manually triggered workstream alert"


class NotificationRule(models.Model):
    """Admin-editable switches for which alerts fire and on what schedule.
    One row per rule_type (except DEADLINE_REMINDER, which may have several
    rows -- one per reminder window, e.g. 1/3/7/14 days before)."""

    rule_type = models.CharField(max_length=30, choices=RuleType.choices)
    days_before = models.PositiveSmallIntegerField(
        null=True, blank=True, help_text="Used by Deadline reminder: days before the end date to alert."
    )
    threshold = models.PositiveSmallIntegerField(
        null=True, blank=True, help_text="Used by Workstream overdue: number of overdue activities that triggers an alert."
    )
    enabled = models.BooleanField(default=True)

    class Meta:
        ordering = ["rule_type", "days_before"]
        constraints = [
            models.UniqueConstraint(
                fields=["rule_type", "days_before"], name="unique_rule_type_days_before"
            )
        ]

    def __str__(self):
        label = self.get_rule_type_display()
        if self.days_before is not None:
            label += f" ({self.days_before}d)"
        return label


class NotificationLog(models.Model):
    rule_type = models.CharField(max_length=30, choices=RuleType.choices)
    activity = models.ForeignKey(
        "activities.Activity", on_delete=models.CASCADE, null=True, blank=True, related_name="notifications"
    )
    workstream = models.ForeignKey(
        "projects.Workstream", on_delete=models.CASCADE, null=True, blank=True, related_name="notifications"
    )
    recipient_email = models.EmailField()
    subject = models.CharField(max_length=255)
    status = models.CharField(
        max_length=10,
        choices=[("SENT", "Sent"), ("FAILED", "Failed")],
        default="SENT",
    )
    error = models.TextField(blank=True)
    sent_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-sent_at"]
        indexes = [models.Index(fields=["rule_type", "activity", "sent_at"])]

    def __str__(self):
        return f"{self.rule_type} -> {self.recipient_email} ({self.sent_at:%Y-%m-%d})"
