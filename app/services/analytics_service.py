from app.models import Event, Registration, User
from sqlalchemy import func
from datetime import datetime, timedelta


class AnalyticsService:
    """Analytics and statistics service"""

    @staticmethod
    def get_organizer_performance(organizer_id):
        """Get organizer performance metrics"""
        events    = Event.query.filter_by(organizer_id=organizer_id).all()
        event_ids = [e.id for e in events]

        if not event_ids:
            return {
                'total_events':        0,
                'total_registrations': 0,
                'total_revenue':       0,
                'avg_attendance':      0,
                'popular_category':    'N/A'
            }

        total_registrations = Registration.query.filter(
            Registration.event_id.in_(event_ids)
        ).count()

        total_revenue = sum([
            e.price * Registration.query.filter_by(event_id=e.id).count()
            for e in events if e.is_paid
        ])

        attended = Registration.query.filter(
            Registration.event_id.in_(event_ids),
            Registration.attended == True
        ).count()

        avg_attendance = (attended / total_registrations * 100) if total_registrations > 0 else 0

        from collections import Counter
        categories       = Counter([e.category for e in events])
        popular_category = categories.most_common(1)[0][0] if categories else 'N/A'

        return {
            'total_events':        len(events),
            'total_registrations': total_registrations,
            'total_revenue':       total_revenue,
            'avg_attendance':      round(avg_attendance, 1),
            'popular_category':    popular_category
        }

    @staticmethod
    def get_event_statistics(event_id):
        """Get detailed event statistics"""
        event = Event.query.get(event_id)
        if not event:
            return None

        registrations = Registration.query.filter_by(event_id=event_id).all()

        return {
            'total_registrations': len(registrations),
            'confirmed':           len([r for r in registrations if r.status == 'confirmed']),
            'waitlist':            len([r for r in registrations if r.status == 'waitlist']),
            'attended':            len([r for r in registrations if r.attended]),
            'cancelled':           len([r for r in registrations if r.status == 'cancelled']),
            'revenue':             event.price * len([r for r in registrations if r.payment_status == 'paid']),
            'capacity_percentage': (
                (event.max_participants - event.available_seats) / event.max_participants * 100
                if event.max_participants > 0 else 0
            )
        }

    @staticmethod
    def get_admin_statistics():
        """Get admin dashboard statistics"""
        from collections import Counter

        today = datetime.utcnow().date()

        # User stats
        total_users     = User.query.count()
        new_users_today = User.query.filter(
            func.date(User.created_at) == today
        ).count()

        # Event stats
        total_events  = Event.query.count()
        active_events = Event.query.filter_by(is_active=True).count()

        # Registration stats
        total_registrations = Registration.query.count()
        registrations_today = Registration.query.filter(
            func.date(Registration.created_at) == today   # ✅ Fixed: was registration_date
        ).count()

        # Revenue
        paid_events   = Event.query.filter_by(is_paid=True).all()
        total_revenue = sum([
            e.price * Registration.query.filter_by(
                event_id=e.id, payment_status='paid'
            ).count()
            for e in paid_events
        ])

        # User growth — last 7 days
        user_growth_labels = []
        user_growth_data   = []
        for i in range(6, -1, -1):
            day   = today - timedelta(days=i)
            count = User.query.filter(func.date(User.created_at) == day).count()
            user_growth_labels.append(day.strftime('%d %b'))
            user_growth_data.append(count)

        # Category distribution
        all_events = Event.query.all()
        categories = Counter([e.category for e in all_events if e.category])

        return {
            'total_users':          total_users,
            'new_users_today':      new_users_today,
            'total_events':         total_events,
            'active_events':        active_events,
            'total_registrations':  total_registrations,
            'registrations_today':  registrations_today,
            'total_revenue':        total_revenue,
            'user_growth_labels':   user_growth_labels,
            'user_growth_data':     user_growth_data,
            'category_labels':      list(categories.keys()),
            'category_data':        list(categories.values())
        }
