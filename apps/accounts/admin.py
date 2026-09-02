from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    list_display = ("username", "email", "first_name", "last_name", "role", "is_active", "is_staff")
    list_filter = ("role", "is_active", "is_staff")
    fieldsets = DjangoUserAdmin.fieldsets + (
        ("Census Tracker", {"fields": ("role", "phone", "receive_email_notifications")}),
    )
    add_fieldsets = DjangoUserAdmin.add_fieldsets + (
        ("Census Tracker", {"fields": ("role", "phone", "email")}),
    )
