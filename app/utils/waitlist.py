from app.models import Registration
from app.extensions import db

def promote_from_waitlist(event):
    """
    When a seat opens, promote the oldest waitlisted registration to confirmed.
    Returns the promoted Registration object, or None.
    """
    if event.available_seats <= 0:
        return None

    next_in_line = Registration.query.filter_by(
        event_id=event.id,
        status='waitlist'
    ).order_by(Registration.created_at.asc()).first()

    if not next_in_line:
        return None

    next_in_line.status = 'confirmed'
    event.available_seats -= 1
    db.session.commit()

    # Sync new count to Firestore
    try:
        from app.utils.firestore_sync import sync_event_seats
        sync_event_seats(event)
    except Exception as e:
        print(f"[Waitlist] Firestore sync failed: {e}")

    return next_in_line
