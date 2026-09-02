from django.contrib import admin

from .models import NotificationLog, NotificationRule


@admin.register(NotificationRule)
class NotificationRuleAdmin(admin.ModelAdmin):
    list_display = ("rule_type", "days_before", "threshold", "enabled")
    list_editable = ("enabled",)
    list_filter = ("rule_type", "enabled")


@admin.register(NotificationLog)
class NotificationLogAdmin(admin.ModelAdmin):
    list_display = ("rule_type", "recipient_email", "subject", "status", "sent_at")
    list_filter = ("rule_type", "status")
    search_fields = ("recipient_email", "subject")
    readonly_fields = [f.name for f in NotificationLog._meta.fields]
