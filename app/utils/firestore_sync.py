# app/utils/firestore_sync.py
"""
Firestore sync with full SQLite fallback.

Every Firebase feature has an equivalent SQLAlchemy implementation.
If Firebase is unavailable/misconfigured, the SQLite path runs instead
and the feature continues working transparently.
"""
import os
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

_firestore_client   = None
_firebase_available = None   # None = untested, True/False = cached result


# ── Availability check (cached after first call) ──────────────────────────────

def _is_firebase_available():
    """Check once and cache whether Firebase Admin SDK is usable."""
    global _firebase_available
    if _firebase_available is not None:
        return _firebase_available

    try:
        import firebase_admin
        from firebase_admin import credentials, firestore
        from flask import current_app

        # Never hardcode paths — always read from config
        cred_path = current_app.config.get('FIREBASE_CREDENTIALS_PATH', '')

        if not cred_path or not os.path.exists(cred_path):
            logger.warning("[Firebase] Credentials file not found: %s", cred_path)
            _firebase_available = False
            return False

        if not firebase_admin._apps:
            cred = credentials.Certificate(cred_path)
            firebase_admin.initialize_app(cred)

        _firebase_available = True
        return True

    except Exception as e:
        logger.warning("[Firebase] Unavailable — using SQLite fallback. Reason: %s", e)
        _firebase_available = False
        return False


def get_firestore():
    """Return Firestore client or None if Firebase is unavailable."""
    global _firestore_client
    if _firestore_client:
        return _firestore_client
    if not _is_firebase_available():
        return None
    try:
        from firebase_admin import firestore
        _firestore_client = firestore.client()
        return _firestore_client
    except Exception as e:
        logger.warning("[Firebase] get_firestore failed: %s", e)
        return None


# ── Feature 6: Real-time Seat Count ──────────────────────────────────────────

def sync_event_seats(event):
    """
    Write seat count + status to Firestore after every registration,
    cancellation, or status change.

    Falls back silently — SQLite is always the source of truth.
    Bugs fixed vs. original:
      - _get_client() → get_firestore()   (undefined name)
      - datetime.utcnow() now available   (import added at top)
      - logger.warning() now available    (logging set up at top)
      - broken else-on-try removed        (else ran on SUCCESS, not fallback)
    """
    fs = get_firestore()
    if not fs:
        logger.info("[Fallback] Seat count for event %s served from SQLite", event.id)
        return

    try:
        fs.collection('events').document(str(event.id)).set({
            'event_id':         event.id,
            'available_seats':  event.available_seats,
            'max_participants': event.max_participants,
            'status':           getattr(event, 'status', 'active') or 'active',
            'status_reason':    getattr(event, 'status_reason', '') or '',
            'postponed_to': (
                event.postponed_to.isoformat()
                if getattr(event, 'postponed_to', None) else None
            ),
            'updated_at': datetime.utcnow().isoformat(),
        }, merge=True)
        logger.debug("[Firebase] Seats synced for event %s", event.id)
    except Exception as e:
        logger.warning("[Firebase] Seat sync failed for event %s: %s", event.id, e)


# ── Feature 3: Real-time Event Status ────────────────────────────────────────

def update_event_status_firestore(event_id, status, reason=''):
    """
    Push status change to Firestore so all open browser tabs update instantly.
    FALLBACK: Status is stored in SQLite event.is_active.
              Template reads from SQLAlchemy on next load / polling.
    """
    fs = get_firestore()
    if fs:
        try:
            fs.collection('events').document(str(event_id)).set({
                'status':        status,
                'status_reason': reason,
                'is_active':     status == 'active',
                'updated_at':    _server_timestamp(),
            }, merge=True)
            logger.info("[Firebase] Status updated for event %s: %s", event_id, status)
        except Exception as e:
            logger.warning("[Firebase] update_event_status failed: %s", e)
            _sqlite_update_event_status(event_id, status)
    else:
        _sqlite_update_event_status(event_id, status)


def _sqlite_update_event_status(event_id, status):
    """SQLite fallback: update is_active on the event row."""
    try:
        from app.models import Event
        from app.extensions import db
        event = Event.query.get(event_id)
        if event:
            event.is_active = (status == 'active')
            db.session.commit()
            logger.info("[Fallback] Event %s status → %s saved to SQLite", event_id, status)
    except Exception as e:
        logger.error("[Fallback] SQLite status update failed: %s", e)


# ── Activity Logging ──────────────────────────────────────────────────────────

def log_activity(activity_type, user_id, user_name, details, metadata=None):
    """
    Log activity to Firestore for the admin activity feed.
    FALLBACK: Write to SQLite ActivityLog table.
    """
    fs = get_firestore()
    if fs:
        try:
            from firebase_admin import firestore as fs_module
            fs.collection('activity_logs').add({
                'activity_type': activity_type,
                'user_id':       user_id,
                'user_name':     user_name,
                'details':       details,
                'metadata':      metadata or {},
                'timestamp':     fs_module.SERVER_TIMESTAMP,
            })
            logger.debug("[Firebase] Activity logged: %s", activity_type)
        except Exception as e:
            logger.warning("[Firebase] log_activity failed: %s", e)
            _sqlite_log_activity(activity_type, user_id, details, metadata)
    else:
        _sqlite_log_activity(activity_type, user_id, details, metadata)


def _sqlite_log_activity(activity_type, user_id, details, metadata=None):
    """SQLite fallback: insert into ActivityLog table."""
    try:
        from app.models import ActivityLog
        from app.extensions import db
        import json
        db.session.add(ActivityLog(
            activity_type=activity_type,
            user_id=user_id,
            details=details,
            metadata_json=json.dumps(metadata or {})
        ))
        db.session.commit()
        logger.debug("[Fallback] Activity logged to SQLite: %s", activity_type)
    except Exception as e:
        logger.error("[Fallback] SQLite activity log failed: %s", e)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _server_timestamp():
    try:
        from firebase_admin import firestore as fs_module
        return fs_module.SERVER_TIMESTAMP
    except Exception:
        return datetime.utcnow().isoformat()
