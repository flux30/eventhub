# app/services/reminder_service.py
"""
Email reminder scheduling service.
Uses APScheduler (Flask-APScheduler) with a SQLAlchemy job store for
persistence across server restarts.

Public API
----------
schedule_event_reminder(event)     → call after event create
cancel_event_reminder(event_id)    → call on event delete / cancel
reschedule_event_reminder(event)   → call when event_date changes
get_reminder_status(event_id)      → dict {scheduled: bool, run_date: str|None}
"""

import logging
from datetime import datetime, timedelta

from flask import current_app

from app.extensions import scheduler

logger = logging.getLogger(__name__)


# ── Configuration ──────────────────────────────────────────────────────────────

REMINDER_HOURS_BEFORE = 24          # Send reminder N hours before event start
JOB_ID_PREFIX         = 'reminder_event_'


# ── Public API ─────────────────────────────────────────────────────────────────

def schedule_event_reminder(event) -> bool:
    """
    Schedule a 24-hour pre-event reminder for all confirmed registrants.

    Uses replace_existing=True so it atomically replaces any prior job for the
    same event_id — safe to call on both create and update paths.

    Skips silently if:
    - event.send_reminders is False (field may not exist — defaults to True)
    - reminder fire time (event_date - 24h) is already in the past

    Returns:
        True  → job successfully scheduled
        False → skipped or failed (event is still saved — this is non-fatal)
    """
    if not getattr(event, 'send_reminders', True):
        logger.debug("Reminders disabled for event %s, skipping.", event.id)
        return False

    remind_at = event.event_date - timedelta(hours=REMINDER_HOURS_BEFORE)

    if remind_at <= datetime.utcnow():
        logger.debug(
            "Reminder time already passed for event %s (remind_at=%s). Skipping.",
            event.id, remind_at.isoformat()
        )
        return False

    job_id = _make_job_id(event.id)

    try:
        scheduler.add_job(
            id=job_id,
            # ── String reference (not callable object) ──────────────────────
            # APScheduler's SQLAlchemy jobstore serializes jobs to SQLite.
            # Passing a callable directly uses pickle, which breaks on server
            # restart if the function's memory address changes.
            # A dotted string path is resolved fresh on each execution — safe.
            func='app.services.reminder_service:_send_reminders_job',
            trigger='date',
            run_date=remind_at,
            args=[event.id],
            replace_existing=True,   # atomic replace — no remove-then-add race
            jobstore='default',
            misfire_grace_time=7200  # fire up to 2 hrs late after server restart
        )
        logger.info(
            "Reminder scheduled: event_id=%s title='%s' run_at=%s UTC",
            event.id, event.title, remind_at.isoformat()
        )
        return True

    except Exception:
        # Non-fatal: event was committed. Only the reminder scheduling failed.
        logger.exception("Failed to schedule reminder for event %s.", event.id)
        return False


def cancel_event_reminder(event_id: int) -> bool:
    """
    Cancel the pending reminder job for an event.

    Safe to call even if no job exists for this event_id — returns False
    silently rather than raising.
    """
    removed = _remove_job_if_exists(_make_job_id(event_id))
    if removed:
        logger.info("Reminder cancelled: event_id=%s", event_id)
    return removed


def reschedule_event_reminder(event) -> bool:
    """
    Cancel current reminder and schedule a fresh one at the new event date.

    Call this specifically when event_date is updated (not on every edit),
    so jobs are not unnecessarily cycled.
    """
    cancel_event_reminder(event.id)
    return schedule_event_reminder(event)


def get_reminder_status(event_id: int) -> dict:
    """
    Return the current scheduler state for an event's reminder.

    Version-safe: APScheduler 3.x uses job.next_run_time (datetime).
    Uses getattr() with fallback so the function degrades gracefully if
    the attribute is renamed in a future APScheduler version.
    """
    try:
        job = scheduler.get_job(_make_job_id(event_id))

        if not job:
            return {'scheduled': False, 'run_date': None}

        # APScheduler 3.x: job.next_run_time is a datetime (or None if paused)
        # getattr provides a safety net against version differences
        next_run_time = getattr(job, 'next_run_time', None)

        return {
            'scheduled': True,
            'run_date': next_run_time.isoformat() if next_run_time else None,
        }

    except Exception:
        # Swallow all errors — this is a status-display function.
        # A broken status check must never crash the caller.
        logger.warning(
            "get_reminder_status failed for event %s.",
            event_id, exc_info=True
        )
        return {'scheduled': False, 'run_date': None}



# ── Internal helpers ───────────────────────────────────────────────────────────

def _make_job_id(event_id: int) -> str:
    """Stable, unique job ID for a given event."""
    return f"{JOB_ID_PREFIX}{event_id}"


def _remove_job_if_exists(job_id: str) -> bool:
    """
    Remove a scheduled job by ID.
    Returns True if the job existed and was removed, False otherwise.
    Never raises — all exceptions are logged as warnings.
    """
    try:
        if scheduler.get_job(job_id):
            scheduler.remove_job(job_id)
            return True
    except Exception:
        logger.warning(
            "Could not remove job '%s'.", job_id, exc_info=True
        )
    return False


# ── Scheduled job entry point ──────────────────────────────────────────────────

def _send_reminders_job(event_id: int) -> None:
    """
    APScheduler entry point — runs in a background thread with no request context.

    ⚠️  DO NOT call create_app() here.
    Calling create_app() creates a second Flask app instance that re-initializes
    all extensions (SQLAlchemy, LoginManager, the scheduler itself), causing
    duplicate scheduler boot, duplicate DB engine creation, and hard-to-debug
    state corruption.

    Instead, use scheduler.app — Flask-APScheduler stores a direct reference to
    the Flask application during scheduler.init_app(app). This reference is
    always valid for the lifetime of the process.
    """
    try:
        # scheduler.app is set by flask_apscheduler.APScheduler.init_app().
        # It is a direct reference to your Flask app — not a proxy.
        app = scheduler.app
        if app is None:
            logger.error(
                "scheduler.app is None for event %s. "
                "Was scheduler.init_app(app) called?", event_id
            )
            return

        with app.app_context():
            _execute_reminders(event_id)

    except Exception:
        # Top-level catch: APScheduler silences job exceptions by default.
        # This ensures the crash is always visible in logs.
        logger.exception(
            "_send_reminders_job crashed unexpectedly for event_id=%s.", event_id
        )


def _execute_reminders(event_id: int) -> None:
    """
    Core dispatch — runs inside an active Flask application context.

    Calls send_event_reminder() which matches the actual email_sender.py
    signature and renders the HTML template with full ORM objects.
    """
    from app.models import Event, Registration
    from app.utils.email_sender import send_event_reminder

    try:
        event = Event.query.get(event_id)

        if not event:
            logger.warning(
                "Reminder job: event %s not found in DB. "
                "It may have been deleted after the job was scheduled.", event_id
            )
            return

        if not event.is_active:
            logger.info(
                "Reminder job: event %s is inactive. Skipping.", event_id
            )
            return

        event_status = getattr(event, 'status', 'active')
        if event_status in ('cancelled', 'postponed'):
            logger.info(
                "Reminder job: event %s status='%s'. Skipping.",
                event_id, event_status
            )
            return

        # Single JOIN query — avoids N+1 on user fetch inside the loop
        registrations = (
            Registration.query
            .filter_by(event_id=event_id, status='confirmed')
            .join(Registration.user)
            .all()
        )

        if not registrations:
            logger.info(
                "Reminder job: no confirmed registrations for event %s.", event_id
            )
            return

        base_url = current_app.config.get('BASE_URL', 'http://localhost:5000')
        sent, failed = 0, 0

        for reg in registrations:
            try:
                # Calls send_event_reminder() from email_sender.py
                # which matches the actual signature: (user_email, user_name,
                # event_title, event_date, event=, user=, registration=, base_url=)
                send_event_reminder(
                    user_email=reg.user.email,
                    user_name=reg.user.name,
                    event_title=event.title,
                    event_date=event.event_date,
                    event=event,
                    user=reg.user,
                    registration=reg,
                    base_url=base_url,
                )
                sent += 1
            except Exception:
                failed += 1
                logger.error(
                    "Reminder email failed: user=%s event=%s",
                    reg.user.email, event_id, exc_info=True
                )

        logger.info(
            "Reminder batch complete: event=%s sent=%d failed=%d total=%d",
            event_id, sent, failed, len(registrations)
        )

    except Exception:
        logger.exception(
            "_execute_reminders crashed for event_id=%s.", event_id
        )
