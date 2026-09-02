from django.conf import settings
from django.db import models


class UploadBatch(models.Model):
    file_name = models.CharField(max_length=255)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="upload_batches"
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)
    project = models.ForeignKey("projects.Project", on_delete=models.CASCADE, related_name="upload_batches")
    workstream = models.ForeignKey(
        "projects.Workstream",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="upload_batches",
        help_text="Set only when a single-worksheet file was uploaded.",
    )
    sheet_names = models.JSONField(default=list, blank=True)
    rows_total = models.PositiveIntegerField(default=0)
    rows_created = models.PositiveIntegerField(default=0)
    rows_updated = models.PositiveIntegerField(default=0)
    rows_skipped = models.PositiveIntegerField(default=0)
    errors = models.JSONField(default=list, blank=True)
    column_mapping = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-uploaded_at"]
        verbose_name = "upload batch"
        verbose_name_plural = "upload batches"

    def __str__(self):
        return f"{self.file_name} ({self.uploaded_at:%Y-%m-%d %H:%M})"
