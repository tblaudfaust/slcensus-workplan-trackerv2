import hashlib
import re

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone


class Status(models.TextChoices):
    NOT_STARTED = "NOT_STARTED", "Not Started"
    ONGOING = "ONGOING", "Ongoing"
    PENDING_VALIDATION = "PENDING_VALIDATION", "Pending Validation"
    COMPLETED = "COMPLETED", "Completed"
    DELAYED = "DELAYED", "Delayed"
    AT_RISK = "AT_RISK", "At Risk"

    @classmethod
    def open_statuses(cls):
        """Statuses that count as "not yet done" for overdue/at-risk math."""
        return [cls.NOT_STARTED, cls.ONGOING, cls.PENDING_VALIDATION, cls.DELAYED, cls.AT_RISK]

    @classmethod
    def contributor_choices(cls):
        """A Contributor can flag work as ready (Pending Validation) but
        cannot mark it Completed themselves -- that's the Workstream
        Owner's call, via the dedicated validate action."""
        return [c for c in cls.choices if c[0] != cls.COMPLETED]


def _normalize_key(*parts):
    raw = "|".join(re.sub(r"\s+", " ", (p or "").strip().lower()) for p in parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class Activity(models.Model):
    project = models.ForeignKey(
        "projects.Project", on_delete=models.CASCADE, related_name="activities"
    )
    workstream = models.ForeignKey(
        "projects.Workstream", on_delete=models.CASCADE, related_name="activities"
    )
    name = models.CharField("Milestone / Activity", max_length=500)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    duration_days = models.PositiveIntegerField(null=True, blank=True)
    dependency = models.TextField("Dependency / Input", blank=True)
    deliverable = models.TextField("Deliverable / Expected Output", blank=True)
    responsible = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="responsible_activities",
        help_text="Matched system user, if the uploaded name matched one.",
    )
    responsible_text = models.CharField(
        "Responsible Person / Team Contact",
        max_length=300,
        blank=True,
        help_text="Raw name/team from the workbook, kept even when it doesn't match a system user.",
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.NOT_STARTED)
    progress_percent = models.PositiveSmallIntegerField(default=0)
    phase = models.CharField(max_length=150, blank=True)
    remarks = models.TextField(blank=True)
    is_milestone = models.BooleanField(
        default=False, help_text="Flags this as a major milestone for completion alerts."
    )
    validated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="validated_activities",
        help_text="Workstream Owner (or above) who validated this as Completed.",
    )
    validated_at = models.DateTimeField(null=True, blank=True)
    source_row_key = models.CharField(max_length=64, editable=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["end_date", "name"]
        indexes = [models.Index(fields=["project", "workstream", "status"])]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        self.source_row_key = _normalize_key(self.workstream_id and str(self.workstream_id), self.name)
        if self.duration_days is None and self.start_date and self.end_date:
            self.duration_days = (self.end_date - self.start_date).days + 1
        super().save(*args, **kwargs)

    @staticmethod
    def build_row_key(workstream_id, name):
        return _normalize_key(str(workstream_id), name)

    def get_absolute_url(self):
        return reverse("activities:detail", args=[self.pk])

    @property
    def is_overdue(self):
        return bool(
            self.end_date
            and self.end_date < timezone.localdate()
            and self.status != Status.COMPLETED
        )

    @property
    def is_due_soon_within(self):
        """Returns the smallest of {today, 7, 14, 30} the activity falls
        within, or None. Used by the dashboard's due-soon buckets."""
        if not self.end_date or self.status == Status.COMPLETED:
            return None
        days = (self.end_date - timezone.localdate()).days
        if days < 0:
            return None
        for bucket in (0, 7, 14, 30):
            if days <= bucket:
                return bucket
        return None

    @property
    def has_owner(self):
        return bool(self.responsible_id or self.responsible_text.strip())

    @property
    def responsible_display(self):
        if self.responsible_id:
            return str(self.responsible)
        return self.responsible_text or "Unassigned"


class ActivityHistory(models.Model):
    activity = models.ForeignKey(Activity, on_delete=models.CASCADE, related_name="history")
    field_name = models.CharField(max_length=50)
    old_value = models.TextField(blank=True)
    new_value = models.TextField(blank=True)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True
    )
    source = models.CharField(
        max_length=20,
        choices=[("MANUAL", "Manual edit"), ("UPLOAD", "Workbook upload")],
        default="MANUAL",
    )
    changed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-changed_at"]
        verbose_name_plural = "activity history"

    def __str__(self):
        return f"{self.activity_id}: {self.field_name} changed"


class Comment(models.Model):
    activity = models.ForeignKey(Activity, on_delete=models.CASCADE, related_name="comments")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    body = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"Comment by {self.user} on {self.activity_id}"
