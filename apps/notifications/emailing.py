import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags

from .models import NotificationLog, NotificationRule, RuleType

logger = logging.getLogger(__name__)


def rule_enabled(rule_type, days_before=None):
    qs = NotificationRule.objects.filter(rule_type=rule_type, enabled=True)
    if days_before is not None:
        qs = qs.filter(days_before=days_before)
    return qs.exists()


def eligible_recipients(*users):
    """Filters out users with no email on file or who opted out."""
    seen = set()
    result = []
    for user in users:
        if not user or not user.email or user.id in seen:
            continue
        if not user.receive_email_notifications:
            continue
        seen.add(user.id)
        result.append(user)
    return result


def send_notification(*, rule_type, template, subject, context, recipients, activity=None, workstream=None):
    """Renders templates/emails/{template}.html, sends to each recipient
    individually (so failures/opt-outs don't block the batch), and logs
    every attempt to NotificationLog."""
    if not recipients:
        return 0

    html_body = render_to_string(f"emails/{template}.html", {**context, "site_name": settings.SITE_NAME, "site_url": settings.SITE_URL})
    text_body = strip_tags(html_body)

    sent = 0
    for user in recipients:
        try:
            message = EmailMultiAlternatives(subject, text_body, to=[user.email])
            message.attach_alternative(html_body, "text/html")
            message.send()
            NotificationLog.objects.create(
                rule_type=rule_type,
                activity=activity,
                workstream=workstream,
                recipient_email=user.email,
                subject=subject,
                status="SENT",
            )
            sent += 1
        except Exception as exc:  # pragma: no cover - network/SMTP failures
            logger.exception("Failed to send %s notification to %s", rule_type, user.email)
            NotificationLog.objects.create(
                rule_type=rule_type,
                activity=activity,
                workstream=workstream,
                recipient_email=user.email,
                subject=subject,
                status="FAILED",
                error=str(exc),
            )
    return sent


def already_sent_today(rule_type, activity):
    from django.utils import timezone

    today = timezone.localdate()
    return NotificationLog.objects.filter(
        rule_type=rule_type, activity=activity, status="SENT", sent_at__date=today
    ).exists()
