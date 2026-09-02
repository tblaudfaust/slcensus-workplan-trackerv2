from django.contrib import admin

from .models import UploadBatch


@admin.register(UploadBatch)
class UploadBatchAdmin(admin.ModelAdmin):
    list_display = (
        "file_name",
        "project",
        "workstream",
        "uploaded_by",
        "uploaded_at",
        "rows_created",
        "rows_updated",
        "rows_skipped",
    )
    list_filter = ("project", "workstream")
    readonly_fields = [f.name for f in UploadBatch._meta.fields]
