"""Shared activity-mutation helpers used by both the manual edit views and
the workbook upload pipeline, so history logging and notification triggers
behave identically regardless of how a change was made."""

from django.utils import timezone

from .models import Activity, ActivityHistory, Status

TRACKED_FIELDS = [
    "name",
    "start_date",
    "end_date",
    "duration_days",
    "dependency",
    "deliverable",
    "responsible_id",
    "responsible_text",
    "status",
    "progress_percent",
    "phase",
    "remarks",
]


def snapshot(activity: Activity) -> dict:
    return {field: getattr(activity, field) for field in TRACKED_FIELDS}


def _display(field, value):
    if value in (None, ""):
        return ""
    if field == "responsible_id":
        from apps.accounts.models import User

        try:
            return str(User.objects.get(pk=value))
        except User.DoesNotExist:
            return str(value)
    if field == "status":
        return Status(value).label
    return str(value)


def record_changes(activity: Activity, before: dict, changed_by=None, source="MANUAL"):
    """Compares `before` (from snapshot()) against the activity's current
    values and writes one ActivityHistory row per changed tracked field.
    Returns {field_name: (old_display, new_display)} for every changed
    field, so callers can both check *whether* a field changed (used to
    decide which notification triggers to fire) and read the before/after
    text (used in status-change emails) without a second lookup."""
    after = snapshot(activity)
    changed = {}
    entries = []
    for field in TRACKED_FIELDS:
        old, new = before.get(field), after.get(field)
        if old != new:
            old_display, new_display = _display(field, old), _display(field, new)
            changed[field] = (old_display, new_display)
            entries.append(
                ActivityHistory(
                    activity=activity,
                    field_name=field,
                    old_value=old_display,
                    new_value=new_display,
                    changed_by=changed_by,
                    source=source,
                    changed_at=timezone.now(),
                )
            )
    if entries:
        ActivityHistory.objects.bulk_create(entries)
    return changed
