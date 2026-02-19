from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from app.models import User, Event, Registration, ActivityLog
from app.extensions import db
from app.decorators import admin_required
from sqlalchemy import func
from datetime import datetime, timedelta


admin_bp = Blueprint('admin', __name__, url_prefix='/admin')


# ── Time helper ───────────────────────────────────────────────────────────────

def get_time_ago(dt):
    """Return a human-readable relative time string."""
    if not dt:
        return "Unknown"
    delta = datetime.utcnow() - dt
    if delta.days > 0:
        return f"{delta.days} day{'s' if delta.days > 1 else ''} ago"
    elif delta.seconds > 3600:
        hours = delta.seconds // 3600
        return f"{hours} hour{'s' if hours > 1 else ''} ago"
    elif delta.seconds > 60:
        minutes = delta.seconds // 60
        return f"{minutes} minute{'s' if minutes > 1 else ''} ago"
    return "Just now"


# ── Dashboard ─────────────────────────────────────────────────────────────────

@admin_bp.route('/dashboard')
@login_required
@admin_required
def dashboard():
    from app.services.analytics_service import AnalyticsService

    stats = AnalyticsService.get_admin_statistics()

    recent_events = Event.query.order_by(Event.created_at.desc()).limit(5).all()

    # ✅ Fixed: use created_at — registration_date does not exist
    recent_registrations = Registration.query.order_by(
        Registration.created_at.desc()
    ).limit(5).all()

    recent_activity = []
    for reg in recent_registrations:
        try:
            recent_activity.append({
                'action':   f"{reg.user.name} registered for {reg.event.title}",
                'time_ago': get_time_ago(reg.created_at)   # ✅ Fixed
            })
        except Exception:
            # Guard against orphaned registrations with missing user/event
            continue

    return render_template('admin/dashboard.html',
                           stats=stats,
                           recent_events=recent_events,
                           recent_activity=recent_activity)


# ── Users ─────────────────────────────────────────────────────────────────────

@admin_bp.route('/users')
@login_required
@admin_required
def manage_users():
    users = User.query.order_by(User.created_at.desc()).all()
    return render_template('admin/users.html', users=users)


@admin_bp.route('/user-details/<int:user_id>')
@login_required
@admin_required
def user_details(user_id):
    user = User.query.get_or_404(user_id)

    if user.role == 'organizer':
        events        = Event.query.filter_by(organizer_id=user_id).all()
        registrations = []
    else:
        events        = []
        registrations = Registration.query.filter_by(user_id=user_id).order_by(
            Registration.created_at.desc()   # ✅ Fixed
        ).all()

    return render_template('admin/user_details.html',
                           user=user,
                           events=events,
                           registrations=registrations)


@admin_bp.route('/change-role/<int:user_id>', methods=['POST'])
@login_required
@admin_required
def change_role(user_id):
    try:
        data = request.get_json() or {}
        user = User.query.get_or_404(user_id)

        if user.id == current_user.id:
            return jsonify({'success': False, 'error': 'Cannot change your own role'}), 400

        new_role = data.get('role')
        if new_role not in ['participant', 'organizer', 'admin']:
            return jsonify({'success': False, 'error': 'Invalid role'}), 400

        user.role = new_role
        db.session.commit()
        return jsonify({'success': True, 'message': f'User role updated to {new_role}'})

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@admin_bp.route('/delete-user/<int:user_id>', methods=['DELETE'])
@login_required
@admin_required
def delete_user(user_id):
    try:
        user = User.query.get_or_404(user_id)

        if user.id == current_user.id:
            return jsonify({'success': False, 'error': 'Cannot delete your own account'}), 400

        Registration.query.filter_by(user_id=user_id).delete()

        if user.role == 'organizer':
            Event.query.filter_by(organizer_id=user_id).delete()

        db.session.delete(user)
        db.session.commit()
        return jsonify({'success': True, 'message': 'User deleted successfully'})

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


# ── Events ────────────────────────────────────────────────────────────────────

@admin_bp.route('/events')
@login_required
@admin_required
def manage_events():
    events = Event.query.order_by(Event.created_at.desc()).all()
    return render_template('admin/events.html', events=events)


@admin_bp.route('/event-details/<int:event_id>')
@login_required
@admin_required
def event_details(event_id):
    event         = Event.query.get_or_404(event_id)
    registrations = Registration.query.filter_by(event_id=event_id).order_by(
        Registration.created_at.desc()   # ✅ Fixed
    ).all()
    return render_template('admin/event_details.html',
                           event=event,
                           registrations=registrations)


@admin_bp.route('/toggle-event/<int:event_id>', methods=['POST'])
@login_required
@admin_required
def toggle_event(event_id):
    try:
        event           = Event.query.get_or_404(event_id)
        event.is_active = not event.is_active
        db.session.commit()
        return jsonify({'success': True, 'is_active': event.is_active})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


# ── Reports & Logs ────────────────────────────────────────────────────────────

@admin_bp.route('/reports')
@login_required
@admin_required
def reports():
    return render_template('admin/reports.html')


@admin_bp.route('/system-logs')
@login_required
@admin_required
def system_logs():
    # Pull from ActivityLog table (Firebase fallback writes here)
    try:
        logs = ActivityLog.query.order_by(
            ActivityLog.created_at.desc()
        ).limit(100).all()
    except Exception:
        logs = []
    return render_template('admin/logs.html', logs=logs)
