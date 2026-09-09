from django.contrib import messages
from django.shortcuts import redirect, render

from apps.accounts import permissions
from apps.accounts.models import User

from .emailing import eligible_recipients, send_notification
from .models import NotificationLog, NotificationRule, RuleType
from .sms import eligible_sms_recipients, send_sms_alert


@permissions.require_permission(permissions.can_manage_notification_settings)
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


@permissions.require_permission(permissions.can_manage_notification_settings)
def broadcast_view(request):
    subject = request.POST.get("subject", "").strip()
    message = request.POST.get("message", "").strip()
    via_email = "via_email" in request.POST
    via_sms = "via_sms" in request.POST

    if not subject or not message:
        messages.error(request, "Broadcast needs both a subject and a message.")
        return redirect("notifications:settings")
    if not via_email and not via_sms:
        messages.error(request, "Pick at least one delivery channel.")
        return redirect("notifications:settings")

    all_users = list(User.objects.filter(is_active=True))
    email_sent = sms_sent = 0

    if via_email:
        email_sent = send_notification(
            rule_type=RuleType.BROADCAST,
            template="broadcast",
            subject=f"[Census Tracker] {subject}",
            context={
                "recipient_name": "team",
                "subject": subject,
                "message": message,
                "triggered_by": request.user.get_full_name() or request.user.username,
            },
            recipients=eligible_recipients(*all_users),
        )

    if via_sms:
        sms_sent = send_sms_alert(
            rule_type=RuleType.BROADCAST,
            message=f"[Census Tracker] {subject}: {message}",
            recipients=eligible_sms_recipients(*all_users),
        )

    messages.success(request, f"Broadcast sent: {email_sent} email(s), {sms_sent} SMS.")
    return redirect("notifications:settings")
