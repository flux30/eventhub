# app/services/storage_service.py
"""
Feature 5 – Unified Event Banner Upload

upload_event_banner(file, event_id)
    ├── Always saves to local disk first (instant fallback)
    ├── Then attempts Firebase Storage upload
    └── Returns (local_filename, firebase_url_or_None)

The caller stores BOTH values on the Event model:
    event.image      = local_filename   ← always set, guaranteed to work
    event.banner_url = firebase_url     ← set only if Firebase succeeded

Templates should prefer banner_url, fall back to image.

Firebase fallback:
    Any Firebase exception is silently caught and logged.
    The function always returns successfully as long as local disk works.
"""

import logging
import os
from datetime import datetime
from pathlib import Path

from flask import current_app
from werkzeug.utils import secure_filename

logger = logging.getLogger(__name__)

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp'}
MAX_FILE_BYTES     = 10 * 1024 * 1024   # 10 MB


# ── Public API ─────────────────────────────────────────────────────────────────

def upload_event_banner(file, event_id=None):
    """
    Upload an event banner image.

    Args:
        file      : werkzeug FileStorage object from request.files
        event_id  : optional int — used to name the Firebase Storage object

    Returns:
        (local_filename: str | None, firebase_url: str | None)

        local_filename is None only if the file is missing or invalid.
        firebase_url   is None if Firebase failed or is not configured.
    """
    if not file or not file.filename:
        return None, None

    if not _allowed(file.filename):
        logger.warning("Rejected upload — extension not allowed: %s", file.filename)
        return None, None

    # Read file bytes once — used for both local save and Firebase upload
    file_bytes = file.read()

    if len(file_bytes) > MAX_FILE_BYTES:
        logger.warning("Rejected upload — file too large: %d bytes", len(file_bytes))
        return None, None

    # ── 1. Always save locally first ──────────────────────────────────────────
    local_filename = _save_locally(file_bytes, file.filename)
    if not local_filename:
        return None, None   # disk write failed — abort entirely

    # ── 2. Try Firebase Storage ───────────────────────────────────────────────
    firebase_url = _upload_to_firebase(file_bytes, file.filename, event_id)

    return local_filename, firebase_url


def delete_event_banner(local_filename=None, firebase_url=None):
    """
    Delete banner from both local disk and Firebase Storage.
    Each deletion is independently wrapped — one failure doesn't stop the other.
    """
    if local_filename:
        _delete_locally(local_filename)

    if firebase_url:
        _delete_from_firebase(firebase_url)


def get_banner_url(event):
    """
    Return the best available URL for an event's banner image.
    Prefers Firebase CDN URL, falls back to local static path.

    Usage in templates: {{ storage_service.get_banner_url(event) }}
    Or pass it from the route as a template variable.
    """
    if event.banner_url:
        return event.banner_url
    if event.image:
        return f"/static/uploads/events/{event.image}"
    return None


# ── Local storage ──────────────────────────────────────────────────────────────

def _allowed(filename):
    ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
    return ext in ALLOWED_EXTENSIONS


def _save_locally(file_bytes, original_filename):
    """Write bytes to static/uploads/events/. Returns filename or None."""
    try:
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S%f')
        filename  = f"{timestamp}_{secure_filename(original_filename)}"
        folder    = Path(current_app.root_path) / 'static' / 'uploads' / 'events'
        folder.mkdir(parents=True, exist_ok=True)

        filepath = folder / filename
        filepath.write_bytes(file_bytes)

        logger.info("Banner saved locally: %s", filename)
        return filename

    except Exception:
        logger.error("Local banner save failed", exc_info=True)
        return None


def _delete_locally(filename):
    try:
        path = Path(current_app.root_path) / 'static' / 'uploads' / 'events' / filename
        if path.exists():
            path.unlink()
            logger.info("Deleted local banner: %s", filename)
    except Exception:
        logger.warning("Failed to delete local banner: %s", filename, exc_info=True)


# ── Firebase Storage ───────────────────────────────────────────────────────────

def _upload_to_firebase(file_bytes, original_filename, event_id=None):
    """
    Upload to Firebase Storage.
    Returns public download URL string, or None on any failure.
    """
    try:
        import firebase_admin
        from firebase_admin import storage as fb_storage

        # Get the default bucket — configured in app factory via
        # firebase_admin.initialize_app(cred, {'storageBucket': '...'})
        bucket = fb_storage.bucket()
        if not bucket:
            logger.warning("Firebase Storage bucket not configured — skipping upload")
            return None

        ext   = original_filename.rsplit('.', 1)[-1].lower()
        ts    = datetime.now().strftime('%Y%m%d%H%M%S%f')
        name  = f"events/event_{event_id}_{ts}.{ext}" if event_id else f"events/{ts}.{ext}"

        blob = bucket.blob(name)
        blob.upload_from_string(
            file_bytes,
            content_type=f"image/{ext if ext != 'jpg' else 'jpeg'}"
        )
        blob.make_public()

        url = blob.public_url
        logger.info("Banner uploaded to Firebase Storage: %s", url)
        return url

    except ImportError:
        logger.warning("firebase_admin not installed — Firebase Storage unavailable")
        return None
    except Exception:
        logger.warning(
            "Firebase Storage upload failed — local file is the fallback",
            exc_info=False   # keep logs clean; not an error, expected fallback
        )
        return None


def _delete_from_firebase(firebase_url):
    """Delete a blob from Firebase Storage by its public URL."""
    try:
        import firebase_admin
        from firebase_admin import storage as fb_storage

        bucket = fb_storage.bucket()
        if not bucket:
            return

        # Extract blob name from URL
        # Public URL format: https://storage.googleapis.com/BUCKET/BLOB_NAME
        from urllib.parse import urlparse, unquote
        path  = urlparse(firebase_url).path          # /BUCKET/BLOB_NAME
        parts = path.split('/', 2)                   # ['', 'BUCKET', 'BLOB_NAME']
        if len(parts) < 3:
            return
        blob_name = unquote(parts[2])

        blob = bucket.blob(blob_name)
        blob.delete()
        logger.info("Deleted Firebase Storage blob: %s", blob_name)

    except Exception:
        logger.warning("Firebase Storage delete failed for %s", firebase_url, exc_info=False)
