from django.conf import settings
from django.db import models
from django.urls import reverse


class Project(models.Model):
    """A census (or other) programme being tracked. Kept first-class so the
    tracker isn't hard-coded to a single workbook -- a second census, or a
    mid-census survey, is just another Project row."""

    name = models.CharField(max_length=200, unique=True)
    description = models.TextField(blank=True)
    census_year = models.PositiveIntegerField(null=True, blank=True)
    census_day = models.DateField(
        null=True,
        blank=True,
        help_text="Reference/enumeration day the dashboard countdown counts down to.",
    )
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="owned_projects",
        help_text="Project Owner accountable for overall delivery; receives the weekly summary email.",
    )
    co_owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="co_owned_projects",
        help_text="Second Project Owner with the same authority and alerts as the primary owner.",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-is_active", "name"]

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("projects:detail", args=[self.pk])


class Workstream(models.Model):
    """One tab of the workbook (General, GIS, HR, ...). Free-form and
    user-creatable so new workstreams don't require a code change."""

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="workstreams")
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    lead = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="led_workstreams",
    )
    backup_lead = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="backup_led_workstreams",
        help_text="Stands in for the Lead -- included on workstream alerts and used as a fallback recipient when an activity has no individually-assigned owner.",
    )
    members = models.ManyToManyField(
        settings.AUTH_USER_MODEL, related_name="workstreams", blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["project", "name"]
        unique_together = [("project", "name")]

    def __str__(self):
        return f"{self.name} ({self.project.name})"

    def get_absolute_url(self):
        return reverse("projects:workstream_detail", args=[self.pk])

    @property
    def percent_complete(self):
        from apps.activities.models import Status

        total = self.activities.count()
        if not total:
            return 0
        completed = self.activities.filter(status=Status.COMPLETED).count()
        return round((completed / total) * 100)
