from app.models import Registration, Event, User
from app.extensions import db
from flask import current_app
from datetime import datetime


class RegistrationService:
    """Registration management — SQLite as source of truth, Firestore as best-effort sync."""

    def __init__(self):
        try:
            from app.firebase.firestore_admin import FirestoreService
            self.firestore = FirestoreService()
        except Exception:
            self.firestore = None

    # ── Register ──────────────────────────────────────────────────────────────

    def register_for_event(self, user_id, event_id):
        """Register a user for an event."""
        try:
            user  = User.query.get(user_id)
            event = Event.query.get(event_id)

            if not user:
                return None, "User not found"
            if not event:
                return None, "Event not found"
            if datetime.utcnow() > event.registration_deadline:
                return None, "Registration deadline has passed"

            existing = Registration.query.filter_by(
                user_id=user_id, event_id=event_id
            ).first()
            if existing:
                return None, "Already registered for this event"

            if event.available_seats <= 0:
                return None, "Event is sold out"

            status = 'confirmed'
            registration = Registration(
                user_id=user_id,
                event_id=event_id,
                status=status,
                payment_status='pending' if event.is_paid else 'not_required'
            )
            db.session.add(registration)
            event.available_seats -= 1
            db.session.commit()

            # Sync to Firestore (best-effort)
            try:
                from app.utils.firestore_sync import sync_event_seats
                sync_event_seats(event)
            except Exception as e:
                current_app.logger.warning(f"Firestore sync failed (non-critical): {e}")

            return registration, None

        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Registration failed: {e}")
            return None, "Registration failed. Please try again."

    # ── Cancel ────────────────────────────────────────────────────────────────

    def cancel_registration(self, user_id, event_id):
        """Cancel a registration and promote from waitlist if applicable."""
        try:
            registration = Registration.query.filter_by(
                user_id=user_id, event_id=event_id
            ).first()

            if not registration:
                return False, "Registration not found"
            if registration.attended:
                return False, "Cannot cancel after attendance"

            event         = Event.query.get(event_id)
            was_confirmed = registration.status == 'confirmed'

            if was_confirmed:
                event.available_seats += 1

                # Promote first waitlisted user
                waitlist_reg = Registration.query.filter_by(
                    event_id=event_id, status='waitlist'
                ).order_by(Registration.created_at.asc()).first()

                if waitlist_reg:
                    waitlist_reg.status = 'confirmed'
                    event.available_seats -= 1
                    current_app.logger.info(f"Promoted from waitlist: {waitlist_reg.id}")

            db.session.delete(registration)
            db.session.commit()

            try:
                from app.utils.firestore_sync import sync_event_seats
                sync_event_seats(event)
            except Exception as e:
                current_app.logger.warning(f"Firestore sync failed: {e}")

            return True, "Registration cancelled successfully"

        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Cancellation failed: {e}")
            return False, "Cancellation failed"

    # ── Attendance ────────────────────────────────────────────────────────────

    def mark_attendance(self, registration_id):
        """Mark a registration as attended."""
        try:
            registration = Registration.query.get(registration_id)
            if not registration:
                return False, "Registration not found"

            if registration.attended:
                return True, "Already marked as attended"

            registration.attended       = True
            registration.attendance_time = datetime.utcnow()
            # Do NOT change status to 'attended' — keeps status as 'confirmed'
            # so seat-count logic stays correct
            db.session.commit()

            current_app.logger.info(f"Attendance marked: registration {registration_id}")
            return True, "Attendance marked successfully"

        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Attendance marking failed: {e}")
            return False, "Failed to mark attendance"

    # ── QR Verification ───────────────────────────────────────────────────────

    def verify_qr_code(self, qr_data):
        """
        Parse QR data and return the matching Registration.

        QR format generated by generate_qr_file():
            REG-{registration_id}-{user_id}-{event_id}

        Example: REG-42-7-3
        """
        try:
            if not qr_data or not qr_data.startswith("REG-"):
                return None, "Invalid QR code format"

            parts = qr_data.split("-")

            # Expected: ['REG', registration_id, user_id, event_id]
            if len(parts) != 4:
                return None, "Invalid QR code format"

            registration_id = int(parts[1])
            user_id         = int(parts[2])
            event_id        = int(parts[3])

            registration = Registration.query.filter_by(
                id=registration_id,
                user_id=user_id,
                event_id=event_id
            ).first()

            if not registration:
                return None, "Registration not found"

            if registration.status == 'cancelled':
                return None, "This registration has been cancelled"

            if registration.status == 'waitlist':
                return None, "This attendee is on the waitlist, not confirmed"

            return registration, None

        except ValueError:
            return None, "Invalid QR code — non-numeric ID"
        except Exception as e:
            current_app.logger.error(f"QR verification failed: {e}")
            return None, "QR verification error"

    # ── Participant stats ─────────────────────────────────────────────────────

    def get_participant_stats(self, user_id):
        all_registrations = Registration.query.filter_by(user_id=user_id).all()

        upcoming = Registration.query.filter_by(user_id=user_id).join(Event).filter(
            Event.event_date > datetime.utcnow()
        ).count()

        attended = Registration.query.filter_by(
            user_id=user_id, attended=True
        ).count()

        registered_categories = {r.event.category for r in all_registrations if r.event}
        recommended_count = Event.query.filter(
            Event.category.in_(registered_categories),
            Event.event_date > datetime.utcnow(),
            Event.is_active == True
        ).count() if registered_categories else 0

        return {
            'total_registrations': len(all_registrations),
            'upcoming_events':     upcoming,
            'attended_events':     attended,
            'recommended_count':   recommended_count,
            'saved_events':        0
        }

    def get_upcoming_registrations(self, user_id, limit=4):
        return Registration.query.filter_by(user_id=user_id).join(Event).filter(
            Event.event_date > datetime.utcnow()
        ).order_by(Event.event_date.asc()).limit(limit).all()

    def get_recommended_events(self, user_id, limit=4):
        registrations = Registration.query.filter_by(user_id=user_id).all()
        categories    = {r.event.category for r in registrations if r.event}

        if not categories:
            return Event.query.filter(
                Event.event_date > datetime.utcnow(),
                Event.is_active == True
            ).order_by(Event.created_at.desc()).limit(limit).all()

        return Event.query.filter(
            Event.category.in_(categories),
            Event.event_date > datetime.utcnow(),
            Event.is_active == True
        ).order_by(Event.event_date.asc()).limit(limit).all()

    def get_event_registrations(self, event_id, status=None):
        query = Registration.query.filter_by(event_id=event_id)
        if status:
            query = query.filter_by(status=status)
        return query.order_by(Registration.created_at.asc()).all()

    def get_user_registrations(self, user_id, status=None):
        query = Registration.query.filter_by(user_id=user_id)
        if status:
            query = query.filter_by(status=status)
        return query.order_by(Registration.created_at.desc()).all()
