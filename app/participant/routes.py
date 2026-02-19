# app/participant/routes.py
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, current_app
from flask_login import login_required, current_user
from app.models import Event, Registration, Feedback
from app.extensions import db
from datetime import datetime
from sqlalchemy import text
import qrcode
import os


participant_bp = Blueprint('participant', __name__, url_prefix='/participant')


# ── QR Helper ─────────────────────────────────────────────────────────────────

def generate_qr_file(registration_id, event_id, user_id):
    """Generate QR PNG on disk and return the filename."""
    qr_data = f"REG-{registration_id}-{user_id}-{event_id}"
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=4
    )
    qr.add_data(qr_data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")

    qr_folder = os.path.join(current_app.root_path, 'static', 'uploads', 'qrcodes')
    os.makedirs(qr_folder, exist_ok=True)

    filename = f"qr_{registration_id}.png"
    img.save(os.path.join(qr_folder, filename))
    return filename


# ── Dashboard ─────────────────────────────────────────────────────────────────

@participant_bp.route('/dashboard')
@login_required
def dashboard():
    from app.services.registration_service import RegistrationService
    rs = RegistrationService()
    return render_template('participant/dashboard.html',
                           stats=rs.get_participant_stats(current_user.id),
                           upcoming_registrations=rs.get_upcoming_registrations(current_user.id),
                           recommended_events=rs.get_recommended_events(current_user.id))


# ── Browse Events ─────────────────────────────────────────────────────────────

@participant_bp.route('/events')
@login_required
def browse_events():
    search_query      = request.args.get('q', '')
    selected_category = request.args.get('category', '')

    # Only show active (bookable) events in browse listings
    query = Event.query.filter_by(is_active=True)
    if search_query:
        query = query.filter(
            Event.title.ilike(f'%{search_query}%') |
            Event.description.ilike(f'%{search_query}%')
        )
    if selected_category:
        query = query.filter_by(category=selected_category)

    events     = query.order_by(Event.event_date).all()
    categories = [c[0] for c in db.session.query(Event.category).distinct().all()]

    return render_template('participant/browse_events.html',
                           events=events,
                           categories=categories,
                           search_query=search_query,
                           selected_category=selected_category)


# ── Event Details ─────────────────────────────────────────────────────────────

@participant_bp.route('/events/<int:event_id>')
@login_required
def event_details(event_id):
    event = Event.query.get_or_404(event_id)

    # BUG FIX: original code redirected ALL is_active=False events away.
    # With Feature 3, cancelled/postponed events have is_active=False but
    # participants who follow a link must still see the status banner.
    # Only redirect for events that are truly removed (no status field set).
    event_status = getattr(event, 'status', 'active') or 'active'
    if not event.is_active and event_status not in ('cancelled', 'postponed', 'completed'):
        flash('Event not found.', 'error')
        return redirect(url_for('participant.browse_events'))

    registration = Registration.query.filter_by(
        user_id=current_user.id, event_id=event_id
    ).first()

    ratings = Feedback.query.filter_by(event_id=event_id).all()
    rating_data = {
        'average': round(sum(r.rating for r in ratings) / len(ratings), 1),
        'count':   len(ratings)
    } if ratings else {'average': 0, 'count': 0}

    # Feature 6: pass public Firebase client config to template
    firebase_config = {
        'apiKey':            current_app.config.get('FIREBASE_API_KEY', ''),
        'authDomain':        current_app.config.get('FIREBASE_AUTH_DOMAIN', ''),
        'projectId':         current_app.config.get('FIREBASE_PROJECT_ID', ''),
        'storageBucket':     current_app.config.get('FIREBASE_STORAGE_BUCKET', ''),
        'messagingSenderId': current_app.config.get('FIREBASE_MESSAGING_SENDER_ID', ''),
        'appId':             current_app.config.get('FIREBASE_APP_ID', ''),
    }

    return render_template('participant/event_details.html',
                           event=event,
                           registration=registration,
                           rating_data=rating_data,
                           firebase_config=firebase_config)


# ── Register for Event ────────────────────────────────────────────────────────

@participant_bp.route('/events/<int:event_id>/register', methods=['POST'])
@login_required
def register_event(event_id):
    event = Event.query.get_or_404(event_id)

    # BUG FIX: block registration on cancelled or postponed events
    event_status = getattr(event, 'status', 'active') or 'active'
    if event_status in ('cancelled', 'postponed'):
        flash('Cannot register — this event has been cancelled or postponed.', 'error')
        return redirect(url_for('participant.event_details', event_id=event_id))

    # Already registered?
    existing = Registration.query.filter_by(
        user_id=current_user.id, event_id=event_id
    ).first()

    if existing:
        if existing.status == 'cancelled':
            # Re-registration after prior cancellation
            if (event.available_seats or 0) <= 0:
                flash('Sorry, this event is now full.', 'error')
                return redirect(url_for('participant.event_details', event_id=event_id))
            existing.status         = 'confirmed'
            existing.payment_status = 'pending' if event.is_paid else 'not_required'
            event.available_seats  -= 1
            db.session.flush()
            existing.qr_code = generate_qr_file(existing.id, event_id, current_user.id)
            db.session.commit()
            db.session.refresh(event)
            _post_registration_tasks(event, existing)
            flash('Registration successful!', 'success')
            return redirect(url_for('participant.view_ticket', registration_id=existing.id))

        flash('You are already registered for this event.', 'warning')
        return redirect(url_for('participant.event_details', event_id=event_id))

    # Deadline passed?
    if datetime.utcnow() > event.registration_deadline:
        flash('Registration deadline has passed.', 'error')
        return redirect(url_for('participant.event_details', event_id=event_id))

    # ── Waitlist path ─────────────────────────────────────────────────────────
    if (event.available_seats or 0) <= 0:
        if event.allow_waitlist:
            registration = Registration(
                user_id=current_user.id,
                event_id=event_id,
                status='waitlist',
                payment_status='not_required'
            )
            db.session.add(registration)
            db.session.commit()

            try:
                from app.utils.email_sender import send_waitlist_confirmation
                send_waitlist_confirmation(
                    user_email=current_user.email,
                    user_name=current_user.name,
                    event_title=event.title,
                    event_date=event.event_date,
                    event=event,
                    user=current_user,
                )
            except Exception as e:
                current_app.logger.warning("Waitlist confirmation email failed: %s", e)

            flash("Event is full — you've been added to the waitlist!", 'warning')
            return redirect(url_for('participant.event_details', event_id=event_id))

        flash('Sorry, this event is full.', 'error')
        return redirect(url_for('participant.event_details', event_id=event_id))

    # ── Atomic seat decrement — prevents race conditions ──────────────────────
    result = db.session.execute(
        text("""
            UPDATE events
            SET available_seats = available_seats - 1
            WHERE id = :event_id
              AND available_seats > 0
        """),
        {'event_id': event_id}
    )
    db.session.flush()

    if result.rowcount == 0:
        db.session.rollback()
        flash('Sorry, this event just became full.', 'error')
        return redirect(url_for('participant.event_details', event_id=event_id))

    try:
        registration = Registration(
            user_id=current_user.id,
            event_id=event_id,
            status='confirmed',
            payment_status='pending' if event.is_paid else 'not_required'
        )
        db.session.add(registration)
        db.session.flush()   # populate registration.id before QR generation

        registration.qr_code = generate_qr_file(registration.id, event_id, current_user.id)
        db.session.commit()

        db.session.refresh(event)
        _post_registration_tasks(event, registration)

        flash('Registration successful!', 'success')
        return redirect(url_for('participant.view_ticket', registration_id=registration.id))

    except Exception as e:
        db.session.rollback()
        current_app.logger.error("Registration failed for event %s: %s", event_id, e)
        flash('Registration failed. Please try again.', 'error')
        return redirect(url_for('participant.event_details', event_id=event_id))


def _post_registration_tasks(event, registration):
    """
    Non-critical post-registration tasks.
    Each step is independently wrapped — one failing never stops the others.
    """
    # 1. Sync seat count to Firestore (Feature 6)
    try:
        from app.utils.firestore_sync import sync_event_seats
        sync_event_seats(event)
    except Exception as e:
        current_app.logger.warning("Firestore seat sync failed: %s", e)

    # 2. Registration confirmation email
    try:
        from app.utils.email_sender import send_registration_confirmation
        send_registration_confirmation(
            user_email=registration.user.email,
            user_name=registration.user.name,
            event_title=event.title,
            event_date=event.event_date,
            event=event,
            user=registration.user,
            registration=registration,
        )
    except Exception as e:
        current_app.logger.warning("Confirmation email failed: %s", e)

    # 3. Log activity
    try:
        from app.utils.firestore_sync import log_activity
        log_activity(
            activity_type='event_registered',
            user_id=registration.user_id,
            user_name=registration.user.name,
            details=f"{registration.user.name} registered for '{event.title}'",
            metadata={'event_id': event.id, 'registration_id': registration.id}
        )
    except Exception as e:
        current_app.logger.warning("Activity log on registration failed: %s", e)


# ── View Ticket ───────────────────────────────────────────────────────────────

@participant_bp.route('/ticket/<int:registration_id>')
@login_required
def view_ticket(registration_id):
    registration = Registration.query.get_or_404(registration_id)

    if registration.user_id != current_user.id:
        flash('Access denied.', 'error')
        return redirect(url_for('participant.my_registrations'))

    # Auto-fix: old base64 stored in DB → regenerate as file
    if registration.qr_code and registration.qr_code.startswith('data:image'):
        try:
            registration.qr_code = generate_qr_file(
                registration.id, registration.event_id, registration.user_id
            )
            db.session.commit()
        except Exception as e:
            current_app.logger.warning("QR re-generation (base64) failed: %s", e)

    # Auto-fix: filename in DB but file deleted from disk → regenerate
    elif registration.qr_code:
        qr_path = os.path.join(
            current_app.root_path, 'static', 'uploads', 'qrcodes', registration.qr_code
        )
        if not os.path.exists(qr_path):
            try:
                registration.qr_code = generate_qr_file(
                    registration.id, registration.event_id, registration.user_id
                )
                db.session.commit()
            except Exception as e:
                current_app.logger.warning("QR re-generation (missing file) failed: %s", e)

    # Auto-fix: no QR at all → generate fresh
    else:
        try:
            registration.qr_code = generate_qr_file(
                registration.id, registration.event_id, registration.user_id
            )
            db.session.commit()
        except Exception as e:
            current_app.logger.warning("QR generation failed: %s", e)

    return render_template('participant/view_ticket.html', registration=registration)


# ── My Registrations ──────────────────────────────────────────────────────────

@participant_bp.route('/registrations')
@login_required
def my_registrations():
    registrations = Registration.query.filter_by(
        user_id=current_user.id
    ).order_by(Registration.created_at.desc()).all()
    return render_template('participant/my_registrations.html',
                           registrations=registrations)


# ── Cancel Registration ───────────────────────────────────────────────────────

@participant_bp.route('/cancel-registration/<int:registration_id>', methods=['POST'])
@login_required
def cancel_registration(registration_id):
    registration = Registration.query.get_or_404(registration_id)

    if registration.user_id != current_user.id:
        flash('Access denied.', 'error')
        return redirect(url_for('participant.my_registrations'))

    if registration.attended:
        flash('Cannot cancel — you have already attended this event.', 'error')
        return redirect(url_for('participant.my_registrations'))

    # Snapshot BEFORE deletion — ORM attributes inaccessible after commit
    was_confirmed  = registration.status == 'confirmed'
    event          = registration.event
    event_id       = event.id
    cancelled_user = registration.user

    try:
        # Delete QR file from disk
        if registration.qr_code and not registration.qr_code.startswith('data:'):
            qr_path = os.path.join(
                current_app.root_path, 'static', 'uploads', 'qrcodes',
                registration.qr_code
            )
            if os.path.exists(qr_path):
                os.remove(qr_path)

        if was_confirmed:
            event.available_seats = (event.available_seats or 0) + 1

        db.session.delete(registration)
        db.session.commit()

        if was_confirmed:
            # BUG FIX: sync updated seat count to Firestore after cancellation.
            # Original code was missing this step — Firestore would show stale count
            # until the next registration event triggered a sync.
            try:
                from app.utils.firestore_sync import sync_event_seats
                db.session.refresh(event)
                sync_event_seats(event)
            except Exception as e:
                current_app.logger.warning("Firestore seat sync on cancel failed: %s", e)

            # 1. Cancellation confirmation email to the canceller
            try:
                from app.utils.email_sender import send_cancellation_confirmation
                send_cancellation_confirmation(
                    user_email=cancelled_user.email,
                    user_name=cancelled_user.name,
                    event_title=event.title,
                    event_date=event.event_date,
                    event=event,
                    user=cancelled_user,
                )
            except Exception as e:
                current_app.logger.warning("Cancellation email failed: %s", e)

            # 2. Promote next waitlisted person → confirmed
            # Service handles: QR gen, Firebase sync, ActivityLog, promotion email
            try:
                from app.services.waitlist_service import promote_from_waitlist
                promote_from_waitlist(event_id)
            except Exception as e:
                current_app.logger.warning("Waitlist promotion failed: %s", e)

            # 3. Log cancellation activity
            try:
                from app.utils.firestore_sync import log_activity
                log_activity(
                    activity_type='registration_cancelled',
                    user_id=cancelled_user.id,
                    user_name=cancelled_user.name,
                    details=f"{cancelled_user.name} cancelled registration for '{event.title}'",
                    metadata={'event_id': event_id}
                )
            except Exception as e:
                current_app.logger.warning("Activity log on cancel failed: %s", e)

        flash('Registration cancelled successfully.', 'success')

    except Exception as e:
        db.session.rollback()
        current_app.logger.error("Cancel registration %s failed: %s", registration_id, e)
        flash('Failed to cancel registration.', 'error')

    return redirect(url_for('participant.my_registrations'))


# ── SQLite Polling Fallback API (Feature 6) ───────────────────────────────────

@participant_bp.route('/api/event-status/<int:event_id>')
@login_required
def event_status_api(event_id):
    """
    Polled every 15 s when Firebase is unavailable.
    BUG FIX: original used direct attribute access for status/status_reason/
    postponed_to — these are Feature 3 fields that may not exist on older
    model instances. Using getattr() with safe defaults prevents AttributeError.
    """
    event = Event.query.get_or_404(event_id)
    postponed_to = getattr(event, 'postponed_to', None)
    return jsonify({
        'event_id':         event.id,
        'available_seats':  event.available_seats or 0,
        'max_participants': event.max_participants,
        'is_sold_out':      (event.available_seats or 0) <= 0,
        'status':           getattr(event, 'status', 'active') or 'active',
        'status_reason':    getattr(event, 'status_reason', '') or '',
        'postponed_to':     postponed_to.isoformat() if postponed_to else None,
    })


# ── Recommendations ───────────────────────────────────────────────────────────

@participant_bp.route('/recommendations')
@login_required
def recommendations():
    from app.services.recommendation_service import RecommendationService
    rec_service = RecommendationService()
    return render_template('participant/recommendations.html',
                           events=rec_service.get_recommendations(current_user.id, limit=12))


# ── Submit Feedback ───────────────────────────────────────────────────────────

@participant_bp.route('/events/<int:event_id>/feedback', methods=['POST'])
@login_required
def submit_feedback(event_id):
    registration = Registration.query.filter_by(
        user_id=current_user.id,
        event_id=event_id,
        attended=True
    ).first()
    if not registration:
        return jsonify({'success': False, 'error': 'Must attend event to leave feedback'}), 403

    rating  = request.json.get('rating')
    comment = request.json.get('comment', '')

    if not rating or not (1 <= int(rating) <= 5):
        return jsonify({'success': False, 'error': 'Rating must be between 1 and 5'}), 400

    try:
        feedback = Feedback.query.filter_by(
            user_id=current_user.id, event_id=event_id
        ).first()
        if feedback:
            feedback.rating  = rating
            feedback.comment = comment
        else:
            db.session.add(Feedback(
                user_id=current_user.id,
                event_id=event_id,
                rating=int(rating),
                comment=comment
            ))
        db.session.commit()
        return jsonify({'success': True, 'message': 'Feedback submitted'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
