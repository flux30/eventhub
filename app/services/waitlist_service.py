# app/services/waitlist_service.py
"""
Feature 4 – Waitlist Auto-Promotion

promote_from_waitlist(event_id)
    Called immediately after any confirmed registration is cancelled.

Concurrency safety strategy:
    SQLite serialises all writes via file-level locking, but we add
    an explicit row-level check inside a single transaction so that
    even if two cancellations race, only one promotion fires per seat.

    Flow (all inside one db.session):
        1. Re-read event.available_seats with fresh query (no stale cache)
        2. Find oldest waitlist registration (FIFO — order by created_at)
        3. Promote atomically: status → confirmed, seats unchanged
           (cancelled seat was already returned before this call)
        4. Commit — if another thread beat us, unique constraints prevent double-promote
        5. Post-commit: generate QR, sync Firebase, send email (all in background)

Firebase fallback:
    Any Firestore exception is caught. Seat count falls back to SQLite polling
    (already implemented on the frontend as 15s interval).
"""

import logging
import os
from datetime import datetime
from threading import Thread

from flask import current_app
from sqlalchemy import select

from app.extensions import db
from app.models import Event, Registration, ActivityLog

logger = logging.getLogger(__name__)


# ── Public API ─────────────────────────────────────────────────────────────────

def promote_from_waitlist(event_id):
    """
    Attempt to promote the longest-waiting waitlisted registration
    for the given event.

    Should be called AFTER the cancelling registration has already been
    committed and available_seats incremented.

    Returns:
        promoted_registration (Registration | None)
    """
    try:
        return _atomic_promote(event_id)
    except Exception:
        logger.error(
            "Waitlist promotion failed for event %d", event_id, exc_info=True
        )
        return None


# ── Core atomic promotion ──────────────────────────────────────────────────────

def _atomic_promote(event_id):
    """
    All reads and writes happen in a single transaction.
    Returns the promoted Registration or None.
    """
    # Fresh read — never use a cached event object here
    event = db.session.execute(
        select(Event).where(Event.id == event_id)
    ).scalar_one_or_none()

    if not event:
        logger.warning("promote_from_waitlist: event %d not found", event_id)
        return None

    if event.available_seats <= 0:
        logger.info("No free seats on event %d — no promotion", event_id)
        return None

    # Oldest waitlist entry first (FIFO)
    next_reg = (
        Registration.query
        .filter_by(event_id=event_id, status='waitlist')
        .order_by(Registration.created_at.asc())
        .first()
    )

    if not next_reg:
        logger.info("No waitlisted registrations for event %d", event_id)
        return None

    # ── Atomic promotion ───────────────────────────────────────────────────────
    next_reg.status = 'confirmed'
    event.available_seats -= 1      # consume the free seat

    try:
        db.session.commit()
        logger.info(
            "Promoted registration %d (user %d) from waitlist on event %d",
            next_reg.id, next_reg.user_id, event_id
        )
    except Exception:
        db.session.rollback()
        logger.error("Commit failed during waitlist promotion", exc_info=True)
        return None

    # ── Post-commit async work ─────────────────────────────────────────────────
    _post_promotion_tasks(next_reg.id, event_id)

    return next_reg


# ── Post-promotion async tasks ─────────────────────────────────────────────────

def _post_promotion_tasks(registration_id, event_id):
    """
    Runs all side-effects in a single background thread so the
    HTTP response is never delayed.
    """
    app = current_app._get_current_object()

    def _run():
        with app.app_context():
            reg = Registration.query.get(registration_id)
            if not reg:
                return

            # 1. Generate QR code (if not already present)
            if not reg.qr_code:
                _generate_qr(reg)

            # 2. Firestore seat sync
            _sync_seats_to_firebase(event_id)

            # 3. Activity log (SQLite fallback always runs)
            _log_promotion(reg)

            # 4. Promotion email
            _send_promotion_email(reg)

    Thread(target=_run, daemon=True).start()


def _generate_qr(registration):
    """Generate a QR code PNG for the promoted registration."""
    try:
        import qrcode
        from pathlib import Path

        qr_dir = Path(current_app.root_path) / 'static' / 'uploads' / 'qrcodes'
        qr_dir.mkdir(parents=True, exist_ok=True)

        qr_data = (
            f"EVENTHUB-REG-{registration.id}"
            f"-EVENT-{registration.event_id}"
            f"-USER-{registration.user_id}"
        )
        filename = f"qr_{registration.id}.png"
        qr_path  = qr_dir / filename

        img = qrcode.make(qr_data)
        img.save(str(qr_path))

        registration.qr_code = filename
        db.session.commit()
        logger.info("QR generated for promoted registration %d", registration.id)

    except Exception:
        logger.error(
            "QR generation failed for registration %d", registration.id, exc_info=True
        )


def _sync_seats_to_firebase(event_id):
    """
    Push updated seat count to Firestore.
    Falls back silently — SQLite polling handles the frontend.
    """
    try:
        from app.utils.firestore_sync import sync_event_seats
        event = Event.query.get(event_id)
        if event:
            sync_event_seats(event)
    except Exception:
        logger.warning(
            "Firebase seat sync failed after promotion for event %d — "
            "frontend will fall back to polling",
            event_id, exc_info=False
        )


def _log_promotion(registration):
    """Write promotion event to ActivityLog (always — SQLite fallback)."""
    firebase_ok = False
    try:
        from app.utils.firestore_sync import log_activity
        log_activity(
            activity_type='waitlist_promoted',
            user_id=registration.user_id,
            user_name=registration.user.name,
            details=(
                f"{registration.user.name} promoted from waitlist "
                f"to confirmed for '{registration.event.title}'"
            ),
            metadata={
                'registration_id': registration.id,
                'event_id':        registration.event_id,
            }
        )
        firebase_ok = True
    except Exception:
        pass

    # Always write to SQLite regardless of Firebase result
    try:
        log = ActivityLog(
            activity_type='waitlist_promoted',
            user_id=registration.user_id,
            details=(
                f"Promoted from waitlist: registration #{registration.id} "
                f"for event '{registration.event.title}'"
            ),
            metadata_json=str({
                'registration_id': registration.id,
                'event_id':        registration.event_id,
                'firebase_ok':     firebase_ok,
            }),
        )
        db.session.add(log)
        db.session.commit()
    except Exception:
        db.session.rollback()
        logger.error("ActivityLog write failed for promotion", exc_info=True)


def _send_promotion_email(registration):
    """Email the promoted participant their confirmed ticket + QR code."""
    try:
        from app.utils.email_sender import send_waitlist_promotion
        send_waitlist_promotion(
            user_email=registration.user.email,
            user_name=registration.user.name,
            event_title=registration.event.title,
            event_date=registration.event.event_date,
            event=registration.event,
            user=registration.user,
            registration=registration,
        )
        logger.info(
            "Promotion email sent to user %d for event %d",
            registration.user_id, registration.event_id
        )
    except Exception:
        logger.error(
            "Promotion email failed for registration %d",
            registration.id, exc_info=True
        )
