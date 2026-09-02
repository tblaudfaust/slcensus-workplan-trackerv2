from django.contrib import admin

from .models import Project, Workstream


class WorkstreamInline(admin.TabularInline):
    model = Workstream
    extra = 0
    fields = ("name", "lead")


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ("name", "census_year", "owner", "is_active", "created_at")
    list_filter = ("is_active",)
    search_fields = ("name",)
    inlines = [WorkstreamInline]


@admin.register(Workstream)
class WorkstreamAdmin(admin.ModelAdmin):
    list_display = ("name", "project", "lead")
    list_filter = ("project",)
    search_fields = ("name",)
    filter_horizontal = ("members",)
