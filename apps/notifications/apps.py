import os
import sys

from django.apps import AppConfig
from django.conf import settings


class NotificationsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.notifications"

    def ready(self):
        from django.db.models.signals import post_migrate

        from . import signal_handlers  # noqa: F401 -- registers the receivers

        post_migrate.connect(_seed_default_rules, sender=self)

        # Guard against starting the scheduler twice under the dev
        # autoreloader (which re-executes ready() in the reloader parent
        # process) and against test runs, where a background job firing
        # mid-suite would be flaky and pointless.
        is_reloader_child = os.environ.get("RUN_MAIN") == "true"
        running_tests = "test" in sys.argv
        if settings.SCHEDULER_ENABLED and not running_tests and (is_reloader_child or not settings.DEBUG):
            from . import scheduler

            scheduler.start()


def _seed_default_rules(sender, **kwargs):
    """Creates one enabled row per non-deadline rule type, plus a deadline
    reminder row for each of REMINDER_DAYS_DEFAULT, the first time
    migrations run. Leaves everything alone on subsequent migrates so an
    admin's later edits in the Notification Settings page always stick."""
    from .models import NotificationRule, RuleType

    if NotificationRule.objects.exists():
        return

    for days in settings.REMINDER_DAYS_DEFAULT:
        NotificationRule.objects.get_or_create(
            rule_type=RuleType.DEADLINE_REMINDER, days_before=days, defaults={"enabled": True}
        )

    NotificationRule.objects.get_or_create(
        rule_type=RuleType.WORKSTREAM_OVERDUE,
        days_before=None,
        defaults={"enabled": True, "threshold": settings.WORKSTREAM_OVERDUE_THRESHOLD_DEFAULT},
    )

    for rule_type in (
        RuleType.OVERDUE,
        RuleType.AT_RISK,
        RuleType.STATUS_CHANGE,
        RuleType.TASK_ASSIGNED,
        RuleType.MILESTONE_COMPLETED,
        RuleType.WEEKLY_DIGEST,
    ):
        NotificationRule.objects.get_or_create(rule_type=rule_type, days_before=None, defaults={"enabled": True})
