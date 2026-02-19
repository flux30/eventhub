# app/services/event_service.py
import logging
from datetime import datetime, timedelta
from collections import Counter

from sqlalchemy import func

from app.extensions import db
from app.models import Event, Registration

logger = logging.getLogger(__name__)


# ── Lazy import guard ─────────────────────────────────────────────────────────

def _reminder_fns():
    """
    Returns (schedule_fn, cancel_fn, reschedule_fn).
    Returns (None, None, None) if reminder service is unavailable.
    """
    try:
        from app.services.reminder_service import (
            schedule_event_reminder,
            cancel_event_reminder,
            reschedule_event_reminder,
        )
        return schedule_event_reminder, cancel_event_reminder, reschedule_event_reminder
    except Exception as e:
        logger.warning("Reminder service unavailable: %s", e)
        return None, None, None


class EventService:

    # ── Read operations ───────────────────────────────────────────────────────

    @staticmethod
    def get_event_by_id(event_id):
        return Event.query.get(event_id)

    @staticmethod
    def get_active_events():
        return Event.query.filter_by(is_active=True).all()

    @staticmethod
    def get_upcoming_events(limit=10):
        return (
            Event.query
            .filter(Event.event_date > datetime.utcnow(), Event.is_active == True)
            .order_by(Event.event_date)
            .limit(limit)
            .all()
        )

    @staticmethod
    def search_events(query):
        return (
            Event.query
            .filter(
                Event.title.ilike(f'%{query}%') |
                Event.description.ilike(f'%{query}%')
            )
            .filter_by(is_active=True)
            .all()
        )

    @staticmethod
    def filter_by_category(category):
        return Event.query.filter_by(category=category, is_active=True).all()

    @staticmethod
    def get_organizer_events(organizer_id):
        return (
            Event.query
            .filter_by(organizer_id=organizer_id)
            .order_by(Event.created_at.desc())
            .all()
        )

    # ── Stats ─────────────────────────────────────────────────────────────────

    @staticmethod
    def get_organizer_stats(organizer_id):
        events    = Event.query.filter_by(organizer_id=organizer_id).all()
        event_ids = [e.id for e in events]

        total_events  = len(events)
        active_events = sum(1 for e in events if e.is_active)

        if not event_ids:
            return {
                'total_events':            0,
                'active_events':           0,
                'total_registrations':     0,
                'confirmed_registrations': 0,
                'recent_registrations':    0,
                'attendance_rate':         0.0,
                'total_revenue':           0.0,
                'registration_labels':     [],
                'registration_data':       [],
                'category_labels':         [],
                'category_data':           [],
            }

        total_registrations = (
            Registration.query
            .filter(Registration.event_id.in_(event_ids))
            .count()
        )

        confirmed_registrations = (
            Registration.query
            .filter(
                Registration.event_id.in_(event_ids),
                Registration.status == 'confirmed'
            )
            .count()
        )

        week_ago = datetime.utcnow() - timedelta(days=7)
        recent_registrations = (
            Registration.query
            .filter(
                Registration.event_id.in_(event_ids),
                Registration.status == 'confirmed',
                Registration.created_at >= week_ago
            )
            .count()
        )

        attended = (
            Registration.query
            .filter(
                Registration.event_id.in_(event_ids),
                Registration.attended == True
            )
            .count()
        )
        attendance_rate = (
            round(attended / confirmed_registrations * 100, 1)
            if confirmed_registrations > 0 else 0.0
        )

        revenue_result = (
            db.session.query(func.sum(Event.price))
            .join(Registration, Registration.event_id == Event.id)
            .filter(
                Event.organizer_id == organizer_id,
                Event.is_paid == True,
                Registration.status == 'confirmed'
            )
            .scalar()
        )
        total_revenue = round(float(revenue_result or 0), 2)

        registration_labels = []
        registration_data   = []
        for i in range(6, -1, -1):
            day   = datetime.utcnow().date() - timedelta(days=i)
            count = (
                Registration.query
                .filter(
                    Registration.event_id.in_(event_ids),
                    func.date(Registration.created_at) == day
                )
                .count()
            )
            registration_labels.append(day.strftime('%d %b'))
            registration_data.append(count)

        categories      = Counter(e.category for e in events if e.category)
        category_labels = [c.title() for c in categories.keys()]
        category_data   = list(categories.values())

        return {
            'total_events':            total_events,
            'active_events':           active_events,
            'total_registrations':     total_registrations,
            'confirmed_registrations': confirmed_registrations,
            'recent_registrations':    recent_registrations,
            'attendance_rate':         attendance_rate,
            'total_revenue':           total_revenue,
            'registration_labels':     registration_labels,
            'registration_data':       registration_data,
            'category_labels':         category_labels,
            'category_data':           category_data,
        }

    # ── Write operations ──────────────────────────────────────────────────────

    @staticmethod
    def create_event(
        organizer_id, title, description, category, location,
        event_date, registration_deadline, max_participants,
        banner_url=None, is_paid=False, price=0.0,
        allow_waitlist=False, is_public=True,
    ):
        try:
            event = Event(
                title=title,
                description=description,
                category=category,
                event_date=event_date,
                location=location,
                max_participants=max_participants,
                available_seats=max_participants,
                registration_deadline=registration_deadline,
                is_paid=is_paid,
                price=price,
                banner_url=banner_url,
                organizer_id=organizer_id,
                is_active=True,
                allow_waitlist=allow_waitlist,
                is_public=is_public,
            )
            db.session.add(event)
            db.session.commit()
            logger.info("Event created: id=%s title='%s'", event.id, event.title)

            schedule_fn, _, _ = _reminder_fns()
            if schedule_fn:
                try:
                    schedule_fn(event)
                except Exception as e:
                    logger.error("Reminder scheduling failed for event %s: %s", event.id, e)

            return event, None

        except Exception as e:
            db.session.rollback()
            logger.exception("create_event failed: %s", e)
            return None, str(e)

    @staticmethod
    def update_event(
        event_id, organizer_id, title, description, category,
        location, event_date, registration_deadline, max_participants,
        banner_url=None, is_paid=False, price=0.0,
        # BUG FIX: allow_waitlist and is_public were missing —
        # caused the waitlist toggle to have no effect on edit
        allow_waitlist=None,
        is_public=None,
    ):
        """
        Update an event.
        allow_waitlist / is_public use None-as-sentinel:
          None  → don't touch the existing value
          True/False → explicitly set the new value
        """
        try:
            event = Event.query.get(event_id)
            if not event or event.organizer_id != organizer_id:
                return None, "Event not found or unauthorized"

            date_changed = (event.event_date != event_date)

            # Adjust available_seats when max_participants changes
            if max_participants and max_participants != event.max_participants:
                confirmed_count = Registration.query.filter_by(
                    event_id=event_id, status='confirmed'
                ).count()
                event.available_seats  = max(0, max_participants - confirmed_count)
                event.max_participants = max_participants
            elif max_participants:
                event.max_participants = max_participants

            event.title                 = title
            event.description           = description
            event.category              = category
            event.location              = location
            event.event_date            = event_date
            event.registration_deadline = registration_deadline
            event.is_paid               = is_paid
            event.price                 = price

            if banner_url:
                event.banner_url = banner_url

            # Only update if caller explicitly passed a value
            if allow_waitlist is not None:
                event.allow_waitlist = allow_waitlist
            if is_public is not None:
                event.is_public = is_public

            db.session.commit()
            logger.info(
                "Event updated: id=%s date_changed=%s allow_waitlist=%s",
                event.id, date_changed, event.allow_waitlist
            )

            _, _, reschedule_fn = _reminder_fns()
            if reschedule_fn and date_changed:
                try:
                    reschedule_fn(event)
                except Exception as e:
                    logger.error("Reminder reschedule failed for event %s: %s", event.id, e)

            return event, None

        except Exception as e:
            db.session.rollback()
            logger.exception("update_event failed: %s", e)
            return None, str(e)

    @staticmethod
    def delete_event(event_id, organizer_id):
        try:
            event = Event.query.get(event_id)
            if not event:
                return False, "Event not found"
            if event.organizer_id != organizer_id:
                return False, "Unauthorized"

            Registration.query.filter_by(event_id=event_id).delete()
            db.session.delete(event)
            db.session.commit()
            logger.info("Event deleted: id=%s", event_id)

            _, cancel_fn, _ = _reminder_fns()
            if cancel_fn:
                try:
                    cancel_fn(event_id)
                except Exception as e:
                    logger.error("Reminder cancel failed for event %s: %s", event_id, e)

            return True, "Event deleted successfully"

        except Exception as e:
            db.session.rollback()
            logger.exception("delete_event failed: %s", e)
            return False, str(e)

    @staticmethod
    def toggle_event_status(event_id):
        event = Event.query.get(event_id)
        if not event:
            return None

        event.is_active = not event.is_active
        db.session.commit()
        logger.info("Event %s toggled: is_active=%s", event_id, event.is_active)

        schedule_fn, cancel_fn, _ = _reminder_fns()
        try:
            if not event.is_active and cancel_fn:
                cancel_fn(event.id)
            elif event.is_active and schedule_fn:
                schedule_fn(event)
        except Exception as e:
            logger.error("Toggle reminder management failed for event %s: %s", event_id, e)

        return event

    @staticmethod
    def get_event_statistics(event_id):
        event = Event.query.get(event_id)
        if not event:
            return None

        registrations = Registration.query.filter_by(event_id=event_id).all()
        confirmed  = [r for r in registrations if r.status == 'confirmed']
        waitlisted = [r for r in registrations if r.status == 'waitlist']
        attended   = [r for r in registrations if r.attended]

        capacity_used = event.max_participants - (event.available_seats or 0)
        capacity_pct  = (
            round(capacity_used / event.max_participants * 100, 1)
            if event.max_participants > 0 else 0.0
        )

        return {
            'total_registrations': len(registrations),
            'confirmed':           len(confirmed),
            'waitlist':            len(waitlisted),
            'attended':            len(attended),
            'available_seats':     event.available_seats or 0,
            'capacity_filled':     capacity_pct,
            'attendance_rate': (
                round(len(attended) / len(confirmed) * 100, 1)
                if confirmed else 0.0
            ),
        }
