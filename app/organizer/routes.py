# app/organizer/routes.py
from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, current_app
from flask_login import login_required, current_user
from app.utils.decorators import organizer_required
from app.services.event_service import EventService
from app.services.registration_service import RegistrationService
from app.models import Event, Registration, EventTemplate, Feedback
from app.extensions import db
from datetime import datetime
import os


organizer_bp = Blueprint('organizer', __name__, url_prefix='/organizer')


# ── Banner upload helper (Feature 5) ─────────────────────────────────────────

def _handle_banner_upload(file, event_id=None):
    """
    Upload banner via storage_service.
    Always saves locally first, then attempts Firebase Storage.
    Returns (local_filename, firebase_url).
    """
    if not file or not file.filename:
        return None, None
    try:
        from app.services.storage_service import upload_event_banner
        return upload_event_banner(file, event_id=event_id)
    except Exception as e:
        current_app.logger.warning("Banner upload failed: %s", e)
        return None, None


# ── Dashboard ─────────────────────────────────────────────────────────────────

@organizer_bp.route('/dashboard')
@login_required
@organizer_required
def dashboard():
    event_service = EventService()
    return render_template('organizer/dashboard.html',
                           stats=event_service.get_organizer_stats(current_user.id),
                           my_events=event_service.get_organizer_events(current_user.id))


# ── Create Event ──────────────────────────────────────────────────────────────

@organizer_bp.route('/events/create', methods=['GET', 'POST'])
@login_required
@organizer_required
def create_event():
    if request.method == 'POST':
        try:
            title                     = request.form.get('title', '').strip()
            description               = request.form.get('description', '').strip()
            category                  = request.form.get('category', '').strip()
            event_type                = request.form.get('event_type', 'in-person')
            event_date_str            = request.form.get('event_date')
            event_time_str            = request.form.get('event_time')
            registration_deadline_str = request.form.get('registration_deadline')
            location                  = request.form.get('location', '').strip()
            meeting_link              = request.form.get('meeting_link', '').strip()
            max_participants          = request.form.get('max_participants', type=int)
            min_participants          = request.form.get('min_participants', type=int)
            is_paid                   = request.form.get('is_paid', '0') == '1'
            price                     = request.form.get('price', type=float) if is_paid else 0.0
            tags                      = request.form.get('tags', '').strip()
            requirements              = request.form.get('requirements', '').strip()
            duration                  = request.form.get('duration', type=float)
            send_reminders            = 'send_reminders' in request.form
            allow_waitlist            = 'allow_waitlist' in request.form
            is_public                 = 'is_public' in request.form

            if not all([title, description, category, event_date_str,
                        event_time_str, registration_deadline_str,
                        location, max_participants]):
                flash('Please fill in all required fields.', 'error')
                return render_template('organizer/create_event.html')

            event_datetime        = datetime.strptime(
                f"{event_date_str} {event_time_str}", "%Y-%m-%d %H:%M"
            )
            registration_deadline = datetime.strptime(registration_deadline_str, "%Y-%m-%d")

            if registration_deadline >= event_datetime:
                flash('Registration deadline must be before event date.', 'error')
                return render_template('organizer/create_event.html')

            if event_datetime <= datetime.now():
                flash('Event date must be in the future.', 'error')
                return render_template('organizer/create_event.html')

            local_filename, firebase_url = _handle_banner_upload(
                request.files.get('event_image')
            )

            event = Event(
                title=title,
                description=description,
                category=category,
                event_type=event_type,
                event_date=event_datetime,
                location=location,
                meeting_link=meeting_link if meeting_link else None,
                max_participants=max_participants,
                min_participants=min_participants if min_participants else None,
                available_seats=max_participants,
                registration_deadline=registration_deadline,
                is_paid=is_paid,
                price=price,
                tags=tags if tags else None,
                requirements=requirements if requirements else None,
                duration=duration if duration else None,
                image=local_filename,
                banner_url=firebase_url,
                send_reminders=send_reminders,
                allow_waitlist=allow_waitlist,
                is_public=is_public,
                organizer_id=current_user.id,
                is_active=True,
                status='active',
            )
            db.session.add(event)
            db.session.commit()

            try:
                from app.utils.firestore_sync import sync_event_seats
                sync_event_seats(event)
            except Exception as e:
                current_app.logger.warning("Firestore seed on create failed: %s", e)

            try:
                from app.utils.firestore_sync import log_activity
                log_activity(
                    activity_type='event_created',
                    user_id=current_user.id,
                    user_name=current_user.name,
                    details=f"{current_user.name} created event '{title}'",
                    metadata={
                        'event_id':   event.id,
                        'category':   event.category,
                        'event_date': event.event_date.isoformat()
                    }
                )
            except Exception as e:
                current_app.logger.warning("Activity log failed: %s", e)

            flash('Event created successfully!', 'success')
            return redirect(url_for('organizer.my_events'))

        except ValueError as e:
            flash('Invalid date or time format.', 'error')
            current_app.logger.error("Date parse error: %s", e)
        except Exception as e:
            db.session.rollback()
            flash('Failed to create event. Please try again.', 'error')
            current_app.logger.error("Event creation failed: %s", e)

    return render_template('organizer/create_event.html')


# ── My Events ─────────────────────────────────────────────────────────────────

@organizer_bp.route('/events')
@login_required
@organizer_required
def my_events():
    event_service = EventService()
    return render_template('organizer/my_events.html',
                           events=event_service.get_organizer_events(current_user.id))


# ── Event Details ─────────────────────────────────────────────────────────────

@organizer_bp.route('/events/<int:event_id>')
@login_required
@organizer_required
def event_details(event_id):
    event = Event.query.get_or_404(event_id)
    if event.organizer_id != current_user.id:
        flash('Access denied.', 'error')
        return redirect(url_for('organizer.my_events'))

    registrations = Registration.query.filter_by(event_id=event_id).all()
    confirmed  = [r for r in registrations if r.status == 'confirmed']
    waitlisted = [r for r in registrations if r.status == 'waitlist']
    attended   = [r for r in registrations if r.attended]
    available  = event.available_seats if event.available_seats is not None else event.max_participants
    filled_pct = round(
        ((event.max_participants - available) / event.max_participants) * 100, 1
    ) if event.max_participants > 0 else 0

    stats = {
        'total_registrations': len(registrations),
        'confirmed':           len(confirmed),
        'waitlist':            len(waitlisted),
        'attended':            len(attended),
        'available_seats':     available,
        'capacity_filled':     filled_pct,
    }

    ratings = Feedback.query.filter_by(event_id=event_id).all()
    rating_data = {
        'average': round(sum(r.rating for r in ratings) / len(ratings), 1) if ratings else 0,
        'count':   len(ratings)
    }

    organizer_registration = Registration.query.filter_by(
        event_id=event_id, user_id=current_user.id
    ).first()

    # Feature 6: Firebase config for real-time listener
    firebase_config = {
        'apiKey':            current_app.config.get('FIREBASE_API_KEY', ''),
        'authDomain':        current_app.config.get('FIREBASE_AUTH_DOMAIN', ''),
        'projectId':         current_app.config.get('FIREBASE_PROJECT_ID', ''),
        'storageBucket':     current_app.config.get('FIREBASE_STORAGE_BUCKET', ''),
        'messagingSenderId': current_app.config.get('FIREBASE_MESSAGING_SENDER_ID', ''),
        'appId':             current_app.config.get('FIREBASE_APP_ID', ''),
    }

    return render_template('organizer/event_details.html',
                           event=event,
                           stats=stats,
                           rating_data=rating_data,
                           registration=organizer_registration,
                           firebase_config=firebase_config)


# ── Update Event Status (Feature 3) ──────────────────────────────────────────

@organizer_bp.route('/events/<int:event_id>/status', methods=['POST'])
@login_required
@organizer_required
def update_event_status(event_id):
    event = Event.query.get_or_404(event_id)

    if event.organizer_id != current_user.id:
        flash('Access denied.', 'error')
        return redirect(url_for('organizer.my_events'))

    new_status       = request.form.get('new_status', '').strip()
    reason           = request.form.get('reason', '').strip() or None
    postponed_to_str = request.form.get('postponed_to', '').strip()

    postponed_to = None
    if new_status == 'postponed':
        if not postponed_to_str:
            flash('Please select a new date when postponing an event.', 'error')
            return redirect(url_for('organizer.event_details', event_id=event_id))
        try:
            postponed_to = datetime.strptime(postponed_to_str, '%Y-%m-%dT%H:%M')
        except ValueError:
            flash('Invalid date format for the new event date.', 'error')
            return redirect(url_for('organizer.event_details', event_id=event_id))

    from app.services.event_status_service import update_event_status as svc_update
    success, message = svc_update(
        event_id=event_id,
        new_status=new_status,
        reason=reason,
        postponed_to=postponed_to,
        changed_by_user_id=current_user.id,
    )

    flash(message, 'success' if success else 'error')
    return redirect(url_for('organizer.event_details', event_id=event_id))


# ── Edit Event ────────────────────────────────────────────────────────────────

@organizer_bp.route('/events/<int:event_id>/edit', methods=['GET', 'POST'])
@login_required
@organizer_required
def edit_event(event_id):
    event_service = EventService()
    event = event_service.get_event_by_id(event_id)

    if not event or event.organizer_id != current_user.id:
        flash('Event not found.', 'error')
        return redirect(url_for('organizer.my_events'))

    if request.method == 'POST':
        title            = request.form.get('title', '').strip()
        description      = request.form.get('description', '').strip()
        category         = request.form.get('category')
        location         = request.form.get('location', '').strip()
        event_date_str   = request.form.get('event_date')
        reg_deadline_str = request.form.get('registration_deadline')
        max_participants = request.form.get('max_participants', type=int)
        is_paid          = request.form.get('is_paid') == 'on'
        price            = request.form.get('price', 0.0, type=float)
        allow_waitlist   = 'allow_waitlist' in request.form
        is_public        = 'is_public' in request.form
        # BUG FIX: send_reminders was missing from edit — always reset to False
        send_reminders   = 'send_reminders' in request.form

        try:
            new_event_date   = datetime.strptime(event_date_str, '%Y-%m-%dT%H:%M')
            new_reg_deadline = datetime.strptime(reg_deadline_str, '%Y-%m-%dT%H:%M')
        except ValueError:
            flash('Invalid date format.', 'error')
            return render_template('organizer/edit_event.html', event=event)

        changes = {}
        if event.event_date != new_event_date:
            changes['Date'] = (
                event.event_date.strftime('%d %b %Y %H:%M'),
                new_event_date.strftime('%d %b %Y %H:%M')
            )
        if event.location != location:
            changes['Location'] = (event.location, location)

        uploaded_file = request.files.get('event_image')
        if uploaded_file and uploaded_file.filename:
            new_local, new_firebase = _handle_banner_upload(uploaded_file, event_id=event_id)
            image_filename = new_local if new_local else event.image
            firebase_url   = new_firebase if new_firebase else event.banner_url
        else:
            image_filename = event.image
            firebase_url   = event.banner_url

        updated_event, error = event_service.update_event(
            event_id=event_id,
            organizer_id=current_user.id,
            title=title,
            description=description,
            category=category,
            location=location,
            event_date=new_event_date,
            registration_deadline=new_reg_deadline,
            max_participants=max_participants,
            is_paid=is_paid,
            price=price if is_paid else 0.0,
            allow_waitlist=allow_waitlist,
            is_public=is_public,
            send_reminders=send_reminders,
        )

        if updated_event:
            updated_event.image      = image_filename
            updated_event.banner_url = firebase_url
            db.session.commit()

            try:
                from app.utils.firestore_sync import sync_event_seats
                sync_event_seats(updated_event)
            except Exception as e:
                current_app.logger.warning("Firestore sync on edit failed: %s", e)

            if changes:
                try:
                    from app.utils.email import send_event_update_notification
                    send_event_update_notification(updated_event, changes)
                except Exception as e:
                    current_app.logger.warning("Update notification failed: %s", e)

            flash('Event updated successfully.', 'success')
            return redirect(url_for('organizer.event_details', event_id=event_id))
        else:
            flash(error or 'Update failed.', 'error')

    return render_template('organizer/edit_event.html', event=event)


# ── Delete Event ──────────────────────────────────────────────────────────────

@organizer_bp.route('/events/<int:event_id>/delete', methods=['POST'])
@login_required
@organizer_required
def delete_event(event_id):
    event = Event.query.get(event_id)
    if event and event.organizer_id == current_user.id:
        try:
            from app.services.storage_service import delete_event_banner
            delete_event_banner(
                local_filename=event.image,
                firebase_url=event.banner_url
            )
        except Exception as e:
            current_app.logger.warning("Banner cleanup on delete failed: %s", e)

    event_service = EventService()
    success, message = event_service.delete_event(event_id, current_user.id)
    flash(message, 'success' if success else 'error')
    return redirect(url_for('organizer.my_events'))


# ── View Registrations ────────────────────────────────────────────────────────

@organizer_bp.route('/events/<int:event_id>/registrations')
@login_required
@organizer_required
def view_registrations(event_id):
    event_service = EventService()
    event = event_service.get_event_by_id(event_id)
    if not event or event.organizer_id != current_user.id:
        flash('Event not found.', 'error')
        return redirect(url_for('organizer.my_events'))

    registration_service = RegistrationService()
    return render_template('organizer/registrations.html',
                           event=event,
                           registrations=registration_service.get_event_registrations(event_id))


# ── Attendance ────────────────────────────────────────────────────────────────

@organizer_bp.route('/events/<int:event_id>/attendance')
@login_required
@organizer_required
def attendance(event_id):
    event_service = EventService()
    event = event_service.get_event_by_id(event_id)
    if not event or event.organizer_id != current_user.id:
        flash('Event not found.', 'error')
        return redirect(url_for('organizer.my_events'))

    registration_service = RegistrationService()
    return render_template('organizer/attendance.html',
                           event=event,
                           registrations=registration_service.get_event_registrations(
                               event_id, status='confirmed'
                           ))


# ── QR Scanner ────────────────────────────────────────────────────────────────

@organizer_bp.route('/qr-scanner')
@login_required
@organizer_required
def qr_scanner():
    return render_template('organizer/qr_scanner.html')


@organizer_bp.route('/api/verify-qr', methods=['POST'])
@login_required
@organizer_required
def verify_qr():
    qr_data = request.json.get('qr_data')
    if not qr_data:
        return jsonify({'error': 'No QR data provided'}), 400

    registration_service = RegistrationService()
    registration, error  = registration_service.verify_qr_code(qr_data)
    if not registration:
        return jsonify({'error': error}), 404

    if registration.event.organizer_id != current_user.id:
        return jsonify({'error': 'Unauthorized'}), 403

    already_attended = registration.attended
    success, message = registration_service.mark_attendance(registration.id)

    if success:
        try:
            from app.utils.firestore_sync import log_activity
            log_activity(
                activity_type='attendance_marked',
                user_id=registration.user_id,
                user_name=registration.user.name,
                details=f"{registration.user.name} checked in to '{registration.event.title}'",
                metadata={
                    'event_id':        registration.event_id,
                    'registration_id': registration.id
                }
            )
        except Exception as e:
            current_app.logger.warning("Attendance activity log failed: %s", e)

        return jsonify({
            'success':          True,
            'user_name':        registration.user.name,
            'event_title':      registration.event.title,
            'registration_id':  registration.id,
            'already_attended': already_attended
        })
    return jsonify({'error': message}), 400


# ── Event Templates ───────────────────────────────────────────────────────────

@organizer_bp.route('/templates')
@login_required
@organizer_required
def event_templates():
    templates = EventTemplate.query.filter_by(user_id=current_user.id).all()
    return render_template('organizer/event_templates.html', templates=templates)


@organizer_bp.route('/templates/save', methods=['POST'])
@login_required
@organizer_required
def save_template():
    event_id      = request.form.get('event_id', type=int)
    template_name = request.form.get('template_name', '').strip()
    if not template_name:
        flash('Template name is required.', 'error')
        return redirect(url_for('organizer.my_events'))

    event = Event.query.get_or_404(event_id)
    if event.organizer_id != current_user.id:
        flash('Unauthorized.', 'error')
        return redirect(url_for('organizer.my_events'))

    db.session.add(EventTemplate(
        user_id=current_user.id,
        template_name=template_name,
        title=event.title,
        description=event.description,
        category=event.category,
        location=event.location,
        max_participants=event.max_participants,
        is_paid=event.is_paid,
        price=event.price
    ))
    db.session.commit()
    flash('Template saved successfully.', 'success')
    return redirect(url_for('organizer.event_templates'))


# ── Verify Payment ────────────────────────────────────────────────────────────

@organizer_bp.route('/verify-payment/<int:registration_id>', methods=['POST'])
@login_required
@organizer_required
def verify_payment(registration_id):
    registration = Registration.query.get_or_404(registration_id)
    if registration.event.organizer_id != current_user.id:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403

    try:
        registration.payment_status = 'paid'
        db.session.commit()

        try:
            from app.utils.email_sender import send_payment_confirmation
            send_payment_confirmation(
                user_email=registration.user.email,
                user_name=registration.user.name,
                event_title=registration.event.title,
                event_date=registration.event.event_date,
                event=registration.event,
                user=registration.user,
                registration=registration,
            )
        except Exception as e:
            current_app.logger.warning("Payment confirmation email failed: %s", e)

        try:
            from app.utils.firestore_sync import log_activity
            log_activity(
                activity_type='payment_verified',
                user_id=current_user.id,
                user_name=current_user.name,
                details=(
                    f"Payment verified for {registration.user.name} "
                    f"— '{registration.event.title}'"
                ),
                metadata={
                    'registration_id': registration.id,
                    'event_id':        registration.event_id
                }
            )
        except Exception as e:
            current_app.logger.warning("Activity log on payment failed: %s", e)

        return jsonify({'success': True, 'message': 'Payment verified'})

    except Exception as e:
        db.session.rollback()
        current_app.logger.error("Payment verification failed: %s", e)
        return jsonify({'success': False, 'error': 'Verification failed'}), 500
