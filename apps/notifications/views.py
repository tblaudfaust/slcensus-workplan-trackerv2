from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.shortcuts import redirect, render

from apps.accounts import permissions

from .models import NotificationLog, NotificationRule


@login_required
@user_passes_test(permissions.can_manage_notification_settings)
def settings_view(request):
    if request.method == "POST":
        for rule in NotificationRule.objects.all():
            enabled_key = f"enabled__{rule.pk}"
            days_key = f"days__{rule.pk}"
            threshold_key = f"threshold__{rule.pk}"
            rule.enabled = enabled_key in request.POST
            if days_key in request.POST and request.POST[days_key]:
                rule.days_before = int(request.POST[days_key])
            if threshold_key in request.POST and request.POST[threshold_key]:
                rule.threshold = int(request.POST[threshold_key])
            rule.save()
        messages.success(request, "Notification settings updated.")
        return redirect("notifications:settings")

    rules = NotificationRule.objects.all()
    recent_log = NotificationLog.objects.select_related("activity")[:30]
    return render(request, "notifications/settings.html", {"rules": rules, "recent_log": recent_log})
