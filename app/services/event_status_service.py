# app/services/event_status_service.py
"""
Feature 3 – Event Status System

update_event_status()  →  DB update + Firebase sync + email blast
Firebase fallback      →  Any Firebase error is caught and logged to
                          ActivityLog (SQLite). The request never blocks.
"""

import logging
from datetime import datetime
from threading import Thread

from flask import current_app

from app.extensions import db
from app.models import Event, Registration, ActivityLog
from app.utils.email_sender import send_event_status_change

logger = logging.getLogger(__name__)

VALID_STATUSES = {'active', 'cancelled', 'postponed'}


# ── Public API ─────────────────────────────────────────────────────────────────

def update_event_status(event_id, new_status, reason=None,
                        postponed_to=None, changed_by_user_id=None):
    """
    1. Validates inputs
    2. Writes to SQLite (always — source of truth)
    3. Syncs to Firestore in background (falls back to ActivityLog on failure)
    4. Emails all confirmed + waitlisted registrants in background

    Returns: (success: bool, message: str)
    """
    if new_status not in VALID_STATUSES:
        return False, f"Invalid status '{new_status}'."

    event = Event.query.get(event_id)
    if not event:
        return False, f"Event {event_id} not found."

    if new_status == 'postponed' and not postponed_to:
        return False, "A new date is required when postponing an event."

    old_status = event.status

    # ── 1. Write to SQLite first ───────────────────────────────────────────────
    event.status        = new_status
    event.status_reason = reason or None
    event.updated_at    = datetime.utcnow()

    if new_status == 'cancelled':
        event.cancelled_at = datetime.utcnow()
        event.is_active    = False
    elif new_status == 'postponed':
        event.postponed_to = postponed_to
        event.event_date   = postponed_to   # shift the actual event date too
        event.is_active    = True
        event.cancelled_at = None
    elif new_status == 'active':
        event.is_active    = True
        event.cancelled_at = None

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        logger.error("DB commit failed for event %d status update", event_id, exc_info=True)
        return False, "Database error — status not updated."

    # ── 2. Firebase sync + activity log (background) ──────────────────────────
    _sync_to_firebase_and_log(event, old_status, changed_by_user_id)

    # ── 3. Email blast (background) ───────────────────────────────────────────
    if new_status != 'active':           # no email when simply re-activating
        _blast_status_emails(event, new_status, reason, postponed_to)

    logger.info("Event %d: %s → %s", event_id, old_status, new_status)
    return True, _success_message(new_status, event.title)


# ── Internal helpers ───────────────────────────────────────────────────────────

def _success_message(status, title):
    msgs = {
        'cancelled': f"'{title}' has been cancelled. All registrants will be notified.",
        'postponed': f"'{title}' has been postponed. All registrants will be notified.",
        'active':    f"'{title}' has been re-activated.",
    }
    return msgs.get(status, "Status updated.")


def _sync_to_firebase_and_log(event, old_status, changed_by_user_id):
    """
    Non-blocking: try Firestore → always write ActivityLog regardless.
    """
    app = current_app._get_current_object()

    # Snapshot values before thread runs (avoid detached-instance errors)
    event_id     = event.id
    event_title  = event.title
    new_status   = event.status
    status_reason = event.status_reason
    postponed_to = event.postponed_to
    cancelled_at = event.cancelled_at

    def _run():
        with app.app_context():
            firebase_ok = False

            # ── Try Firestore ──────────────────────────────────────────────
            try:
                from app.utils.firestore_sync import update_event_status_firestore
                update_event_status_firestore(
                    event_id,
                    new_status,
                    status_reason or ''
                )
                firebase_ok = True
            except Exception:
                logger.warning(
                    "Firestore sync failed for event %d — SQLite is source of truth",
                    event_id, exc_info=False
                )

            # ── Always log to ActivityLog (SQLite fallback) ────────────────
            try:
                log = ActivityLog(
                    activity_type='event_status_change',
                    user_id=changed_by_user_id,
                    details=(
                        f"Event '{event_title}' (id={event_id}) "
                        f"status: '{old_status}' → '{new_status}'"
                        + (f" | reason: {status_reason}" if status_reason else "")
                    ),
                    metadata_json=str({
                        'event_id':    event_id,
                        'old_status':  old_status,
                        'new_status':  new_status,
                        'firebase_ok': firebase_ok,
                    }),
                )
                db.session.add(log)
                db.session.commit()
            except Exception:
                db.session.rollback()
                logger.error("ActivityLog write failed for event %d", event_id, exc_info=True)

    Thread(target=_run, daemon=True).start()


def _blast_status_emails(event, new_status, reason, postponed_to):
    """
    Email every confirmed + waitlisted registrant. Runs in background thread.
    """
    app = current_app._get_current_object()

    # Snapshot all needed data before spawning thread
    event_id    = event.id
    event_title = event.title

    def _run():
        with app.app_context():
            registrations = (
                Registration.query
                .filter(
                    Registration.event_id == event_id,
                    Registration.status.in_(['confirmed', 'waitlist'])
                )
                .all()
            )
            for reg in registrations:
                try:
                    send_event_status_change(
                        user_email=reg.user.email,
                        user_name=reg.user.name,
                        event_title=event_title,
                        new_status=new_status,
                        reason=reason,
                        postponed_to=postponed_to,
                    )
                except Exception:
                    logger.error(
                        "Status email failed for user %d event %d",
                        reg.user_id, event_id, exc_info=True
                    )
            logger.info(
                "Status email blast complete: %d recipients for event %d",
                len(registrations), event_id
            )

    Thread(target=_run, daemon=True).start()
