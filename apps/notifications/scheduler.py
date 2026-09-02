"""In-process APScheduler wiring. Started once from NotificationsConfig.ready()
when SCHEDULER_ENABLED=True. Both jobs just invoke the equivalent
manage.py command so the exact same code path is used whether triggered by
the scheduler, cron, or a person running the command by hand."""

import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from django.core.management import call_command

logger = logging.getLogger(__name__)

_scheduler = None


def _run_check_deadlines():
    try:
        call_command("check_deadlines")
    except Exception:
        logger.exception("check_deadlines job failed")


def _run_weekly_digest():
    try:
        call_command("send_weekly_digest")
    except Exception:
        logger.exception("send_weekly_digest job failed")


def start():
    global _scheduler
    if _scheduler is not None:
        return
    _scheduler = BackgroundScheduler(daemon=True)
    _scheduler.add_job(
        _run_check_deadlines,
        CronTrigger(hour=7, minute=0),
        id="check_deadlines",
        replace_existing=True,
    )
    _scheduler.add_job(
        _run_weekly_digest,
        CronTrigger(day_of_week="mon", hour=7, minute=30),
        id="send_weekly_digest",
        replace_existing=True,
    )
    _scheduler.start()
    logger.info("Notification scheduler started (daily deadline check 07:00, weekly digest Mon 07:30).")
