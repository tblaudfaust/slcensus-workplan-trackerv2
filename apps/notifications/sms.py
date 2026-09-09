import base64
import logging

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


class SmsSendError(Exception):
    pass


def _auth_header():
    credentials = f"{settings.SMS_CLIENT_ID}:{settings.SMS_CLIENT_SECRET}"
    encoded = base64.b64encode(credentials.encode()).decode()
    return f"Basic {encoded}"


def normalize_phone(raw):
    """Converts a phone number to the country-code-prefixed digits-only
    format AppHive expects (e.g. "23230123456"). Real workbook/profile data
    shows up in several shapes -- already prefixed with 232, with a leading
    '+', in local 8-digit form, or in local 9-digit form with a leading 0
    -- so this normalizes all of them rather than requiring one exact
    format. Returns None if nothing usable is present."""
    digits = "".join(ch for ch in (raw or "") if ch.isdigit())
    if not digits:
        return None
    if digits.startswith("232"):
        return digits
    if digits.startswith("0") and len(digits) == 9:
        return "232" + digits[1:]
    if len(digits) == 8:
        return "232" + digits
    return digits


def send_sms(to, content, reference=None):
    """Sends a single SMS via the AppHiveSL API (api.sierrahive.com). The
    call only confirms AppHive accepted the message ("pending") -- final
    delivery status arrives later via their callback mechanism, which this
    app doesn't currently receive, so a successful return here means
    "queued for delivery", not "delivered". Raises SmsSendError on any
    failure (disabled, bad number, network/HTTP error) so callers can log
    it consistently alongside email failures."""
    if not settings.SMS_ENABLED:
        raise SmsSendError("SMS sending is disabled (SMS_ENABLED=False)")

    to_number = normalize_phone(to)
    if not to_number:
        raise SmsSendError(f"Invalid destination phone number: {to!r}")

    payload = {
        "From": settings.SMS_SENDER_ID,
        "To": to_number,
        "Content": content,
    }
    if reference:
        payload["Reference"] = reference

    try:
        response = requests.post(
            f"{settings.SMS_API_BASE_URL}/v1/messages/sms",
            json=payload,
            headers={
                "Authorization": _auth_header(),
                "X-Wallet": f"Token {settings.SMS_TOKEN}",
            },
            timeout=10,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise SmsSendError(str(exc)) from exc

    return response.json()


def eligible_sms_recipients(*users):
    """Filters to users who both opted in to SMS (off by default -- unlike
    email, real SMS costs money and is more intrusive) and have a phone
    number on file."""
    seen = set()
    result = []
    for user in users:
        if not user or not user.phone or user.id in seen:
            continue
        if not user.receive_sms_notifications:
            continue
        seen.add(user.id)
        result.append(user)
    return result


def send_sms_alert(*, rule_type, message, recipients, activity=None, workstream=None):
    """Sends `message` by SMS to each recipient, logging every attempt to
    NotificationLog (channel=SMS) exactly like send_notification does for
    email, so both channels show up in one audit trail. Recipients should
    already be filtered via eligible_sms_recipients."""
    from .models import NotificationChannel, NotificationLog

    if not recipients:
        return 0

    reference_id = f"activity-{activity.id}" if activity else f"workstream-{workstream.id}" if workstream else None

    sent = 0
    for user in recipients:
        try:
            send_sms(user.phone, message, reference=reference_id)
            NotificationLog.objects.create(
                rule_type=rule_type,
                activity=activity,
                workstream=workstream,
                channel=NotificationChannel.SMS,
                recipient=user.phone,
                subject=message[:255],
                status="SENT",
            )
            sent += 1
        except SmsSendError as exc:
            logger.warning("Failed to send %s SMS to %s: %s", rule_type, user.phone, exc)
            NotificationLog.objects.create(
                rule_type=rule_type,
                activity=activity,
                workstream=workstream,
                channel=NotificationChannel.SMS,
                recipient=user.phone,
                subject=message[:255],
                status="FAILED",
                error=str(exc),
            )
    return sent
