from django.contrib import admin

from .models import Activity, ActivityHistory, Comment


class HistoryInline(admin.TabularInline):
    model = ActivityHistory
    extra = 0
    readonly_fields = ("field_name", "old_value", "new_value", "changed_by", "source", "changed_at")
    can_delete = False


class CommentInline(admin.TabularInline):
    model = Comment
    extra = 0


@admin.register(Activity)
class ActivityAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "project",
        "workstream",
        "status",
        "progress_percent",
        "end_date",
        "responsible_display",
        "is_overdue",
    )
    list_filter = ("project", "workstream", "status", "is_milestone")
    search_fields = ("name", "responsible_text", "deliverable")
    autocomplete_fields = ("responsible",)
    inlines = [HistoryInline, CommentInline]
    date_hierarchy = "end_date"


@admin.register(ActivityHistory)
class ActivityHistoryAdmin(admin.ModelAdmin):
    list_display = ("activity", "field_name", "old_value", "new_value", "changed_by", "changed_at")
    list_filter = ("field_name", "source")
    readonly_fields = [f.name for f in ActivityHistory._meta.fields]
