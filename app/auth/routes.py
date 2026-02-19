from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify, current_app
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from app.models import User
from app.extensions import db
from app.services.otp_service import OTPService


auth_bp = Blueprint('auth', __name__, url_prefix='/auth')


# ── Helper ────────────────────────────────────────────────────────────────────

def redirect_authenticated_user():
    """Redirect already-logged-in users to their role-appropriate dashboard."""
    if current_user.role == 'admin':
        return redirect(url_for('admin.dashboard'))
    elif current_user.role == 'organizer':
        return redirect(url_for('organizer.dashboard'))
    return redirect(url_for('participant.dashboard'))


# ── Login ─────────────────────────────────────────────────────────────────────

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect_authenticated_user()

    if request.method == 'POST':
        email    = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        remember = bool(request.form.get('remember', False))

        user = User.query.filter_by(email=email).first()

        if user and user.check_password(password):
            if not user.is_active:
                flash('Your account has been deactivated. Contact admin.', 'error')
                return render_template('auth/login.html')

            login_user(user, remember=remember)

            # ── Activity log ──────────────────────────────────────────────────
            try:
                from app.utils.firestore_sync import log_activity
                log_activity(
                    activity_type='user_login',
                    user_id=user.id,
                    user_name=user.name,
                    details=f"{user.name} logged in",
                    metadata={'role': user.role}
                )
            except Exception as e:
                current_app.logger.warning(f"Login activity log failed: {e}")

            # Respect ?next= param (Flask-Login sets this on protected routes)
            next_page = request.args.get('next')
            if next_page:
                return redirect(next_page)

            if user.role == 'admin':
                return redirect(url_for('admin.dashboard'))
            elif user.role == 'organizer':
                return redirect(url_for('organizer.dashboard'))
            return redirect(url_for('participant.dashboard'))

        flash('Invalid email or password.', 'error')

    return render_template('auth/login.html')


# ── Register ──────────────────────────────────────────────────────────────────

@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect_authenticated_user()

    if request.method == 'POST':
        # OTP verification step (form contains otp1/otp2/otp3/otp4)
        if 'otp1' in request.form:
            return _verify_registration_otp()

        # ── Initial registration form ─────────────────────────────────────────
        name             = request.form.get('name', '').strip()
        email            = request.form.get('email', '').strip().lower()
        phone            = request.form.get('phone', '').strip()
        password         = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        role             = request.form.get('role', 'participant')

        if not all([name, email, password, confirm_password]):
            flash('Name, email, and password are required.', 'error')
            return render_template('auth/register.html')

        if password != confirm_password:
            flash('Passwords do not match.', 'error')
            return render_template('auth/register.html')

        if len(password) < 8:
            flash('Password must be at least 8 characters.', 'error')
            return render_template('auth/register.html')

        if User.query.filter_by(email=email).first():
            flash('Email already registered.', 'error')
            return render_template('auth/register.html')

        # Send OTP — OTPService handles the OTP email internally
        success, message = OTPService.send_otp(email, 'verification')

        if success:
            session['pending_registration'] = {
                'name':     name,
                'email':    email,
                'phone':    phone if phone else None,
                'password': password,
                'role':     role
            }
            flash('OTP sent to your email. Please verify to complete registration.', 'success')
            return render_template('auth/register.html', show_otp=True, email=email)

        flash(f'Failed to send OTP: {message}', 'error')

    return render_template('auth/register.html')


def _verify_registration_otp():
    """Verify OTP and create the user account."""
    if 'pending_registration' not in session:
        flash('No pending registration found. Please register again.', 'error')
        return redirect(url_for('auth.register'))

    otp = ''.join([
        request.form.get('otp1', ''),
        request.form.get('otp2', ''),
        request.form.get('otp3', ''),
        request.form.get('otp4', '')
    ])

    reg_data = session['pending_registration']

    if len(otp) != 4 or not otp.isdigit():
        flash('Please enter a valid 4-digit OTP.', 'error')
        return render_template('auth/register.html', show_otp=True, email=reg_data['email'])

    success, message = OTPService.verify_otp(reg_data['email'], otp, 'verification')

    if success:
        try:
            user = User(
                name=reg_data['name'],
                email=reg_data['email'],
                phone=reg_data.get('phone'),
                role=reg_data['role'],
                is_active=True,
                email_verified=True
            )
            user.set_password(reg_data['password'])

            db.session.add(user)
            db.session.commit()

            # ── ✅ Email: Welcome email to new user ───────────────────────────
            try:
                from app.utils.email import send_welcome_email
                send_welcome_email(user)
            except Exception as e:
                current_app.logger.warning(f"Welcome email failed: {e}")

            # ── Activity log ──────────────────────────────────────────────────
            try:
                from app.utils.firestore_sync import log_activity
                log_activity(
                    activity_type='user_registered',
                    user_id=user.id,
                    user_name=user.name,
                    details=f"New {user.role} account created: {user.email}",
                    metadata={'role': user.role, 'email': user.email}
                )
            except Exception as e:
                current_app.logger.warning(f"Registration activity log failed: {e}")

            # ── Clear session cleanly ─────────────────────────────────────────
            logout_user()
            flash('Registration successful! Please login.', 'success')
            saved_flashes = session.get('_flashes', [])
            session.clear()
            session['_flashes'] = saved_flashes

            return redirect(url_for('auth.login'))

        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Registration failed: {e}")
            flash(f'Registration failed: {str(e)}', 'error')
            return render_template('auth/register.html', show_otp=True, email=reg_data['email'])

    flash(message, 'error')
    return render_template('auth/register.html', show_otp=True, email=reg_data['email'])


# ── Resend OTP (registration + password reset) ────────────────────────────────

@auth_bp.route('/resend-otp', methods=['POST'])
def resend_otp():
    if 'pending_registration' in session:
        email   = session['pending_registration']['email']
        purpose = 'verification'
    elif 'password_reset_email' in session:
        email   = session['password_reset_email']
        purpose = 'reset'
    else:
        return jsonify({'success': False, 'message': 'No pending verification'}), 400

    success, message = OTPService.resend_otp(email, purpose)
    return jsonify({'success': success, 'message': message if success else f'Failed: {message}'})


# ── Logout ────────────────────────────────────────────────────────────────────

@auth_bp.route('/logout')
@login_required
def logout():
    # Log before logout_user() clears current_user
    try:
        from app.utils.firestore_sync import log_activity
        log_activity(
            activity_type='user_logout',
            user_id=current_user.id,
            user_name=current_user.name,
            details=f"{current_user.name} logged out",
            metadata={}
        )
    except Exception as e:
        current_app.logger.warning(f"Logout activity log failed: {e}")

    logout_user()
    flash('You have been logged out successfully.', 'success')
    return redirect(url_for('index'))


# ── Profile ───────────────────────────────────────────────────────────────────

@auth_bp.route('/profile')
@login_required
def profile():
    return render_template('auth/profile.html')


@auth_bp.route('/update-profile', methods=['POST'])
@login_required
def update_profile():
    name  = request.form.get('name', '').strip()
    email = request.form.get('email', '').strip().lower()
    phone = request.form.get('phone', '').strip()

    if not name or not email:
        flash('Name and email are required.', 'error')
        return redirect(url_for('auth.profile'))

    existing = User.query.filter(
        User.email == email,
        User.id != current_user.id
    ).first()
    if existing:
        flash('That email is already in use.', 'error')
        return redirect(url_for('auth.profile'))

    current_user.name  = name
    current_user.email = email
    current_user.phone = phone if phone else None
    db.session.commit()

    # Activity log
    try:
        from app.utils.firestore_sync import log_activity
        log_activity(
            activity_type='profile_updated',
            user_id=current_user.id,
            user_name=current_user.name,
            details=f"{current_user.name} updated their profile",
            metadata={}
        )
    except Exception as e:
        current_app.logger.warning(f"Profile update activity log failed: {e}")

    flash('Profile updated successfully.', 'success')
    return redirect(url_for('auth.profile'))


# ── Change Password ───────────────────────────────────────────────────────────

@auth_bp.route('/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    if request.method == 'POST':
        current_pw = request.form.get('current_password', '')
        new_pw     = request.form.get('new_password', '')
        confirm_pw = request.form.get('confirm_password', '')

        if not current_user.check_password(current_pw):
            flash('Current password is incorrect.', 'error')
            return redirect(url_for('auth.change_password'))

        if len(new_pw) < 8:
            flash('New password must be at least 8 characters.', 'error')
            return redirect(url_for('auth.change_password'))

        if new_pw != confirm_pw:
            flash('Passwords do not match.', 'error')
            return redirect(url_for('auth.change_password'))

        current_user.set_password(new_pw)
        db.session.commit()

        # ── ✅ Email: notify user their password was changed ──────────────────
        try:
            from app.utils.email import send_password_changed_notification
            send_password_changed_notification(current_user)
        except Exception as e:
            current_app.logger.warning(f"Password change notification failed: {e}")

        # Activity log
        try:
            from app.utils.firestore_sync import log_activity
            log_activity(
                activity_type='password_changed',
                user_id=current_user.id,
                user_name=current_user.name,
                details=f"{current_user.name} changed their password",
                metadata={}
            )
        except Exception as e:
            current_app.logger.warning(f"Password change activity log failed: {e}")

        flash('Password changed successfully.', 'success')
        return redirect(url_for('auth.profile'))

    return render_template('auth/change_password.html')


# ── Delete Account ────────────────────────────────────────────────────────────

@auth_bp.route('/delete-account', methods=['POST'])
@login_required
def delete_account():
    from app.models import Registration

    # Snapshot user info before deletion — needed for email after logout
    deleted_name  = current_user.name
    deleted_email = current_user.email
    deleted_id    = current_user.id

    try:
        # Cancel all QR files on disk for this user's registrations
        registrations = Registration.query.filter_by(user_id=current_user.id).all()
        for reg in registrations:
            if reg.qr_code and not reg.qr_code.startswith('data:'):
                import os
                qr_path = os.path.join(
                    current_app.root_path, 'static', 'uploads', 'qrcodes', reg.qr_code
                )
                if os.path.exists(qr_path):
                    try:
                        os.remove(qr_path)
                    except Exception:
                        pass

        Registration.query.filter_by(user_id=current_user.id).delete()
        db.session.delete(current_user)
        db.session.commit()

        logout_user()

        # Activity log (user_id = None since account is gone)
        try:
            from app.utils.firestore_sync import log_activity
            log_activity(
                activity_type='account_deleted',
                user_id=None,
                user_name=deleted_name,
                details=f"Account deleted: {deleted_email}",
                metadata={'former_user_id': deleted_id}
            )
        except Exception as e:
            current_app.logger.warning(f"Delete account activity log failed: {e}")

        flash('Your account has been deleted.', 'success')

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Account deletion failed: {e}")
        flash('Failed to delete account. Please try again.', 'error')

    return redirect(url_for('auth.login'))


# ── Forgot Password ───────────────────────────────────────────────────────────

@auth_bp.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if current_user.is_authenticated:
        return redirect_authenticated_user()

    if request.method == 'POST':
        # OTP verification + new password step
        if 'otp1' in request.form:
            return _verify_password_reset()

        email = request.form.get('email', '').strip().lower()

        if not email:
            flash('Email is required.', 'error')
            return render_template('auth/forgot_password.html')

        user = User.query.filter_by(email=email).first()

        # Always show the same message — prevents email enumeration
        if not user:
            flash('If this email is registered, you will receive a reset code.', 'info')
            return render_template('auth/forgot_password.html')

        # OTPService sends the OTP email internally
        success, message = OTPService.send_otp(email, 'reset')

        if success:
            session['password_reset_email'] = email
            flash('Reset code sent to your email.', 'success')
            return render_template('auth/forgot_password.html', show_otp=True, email=email)

        flash(f'Failed to send reset code: {message}', 'error')

    return render_template('auth/forgot_password.html')


def _verify_password_reset():
    """Verify OTP and apply the new password."""
    if 'password_reset_email' not in session:
        flash('No password reset request found. Please try again.', 'error')
        return redirect(url_for('auth.forgot_password'))

    otp = ''.join([
        request.form.get('otp1', ''),
        request.form.get('otp2', ''),
        request.form.get('otp3', ''),
        request.form.get('otp4', '')
    ])

    new_password     = request.form.get('new_password', '')
    confirm_password = request.form.get('confirm_password', '')
    email            = session['password_reset_email']

    if len(otp) != 4 or not otp.isdigit():
        flash('Please enter a valid 4-digit OTP.', 'error')
        return render_template('auth/forgot_password.html', show_otp=True, email=email)

    if not new_password or not confirm_password:
        flash('Please enter and confirm your new password.', 'error')
        return render_template('auth/forgot_password.html', show_otp=True, email=email)

    if new_password != confirm_password:
        flash('Passwords do not match.', 'error')
        return render_template('auth/forgot_password.html', show_otp=True, email=email)

    if len(new_password) < 8:
        flash('Password must be at least 8 characters.', 'error')
        return render_template('auth/forgot_password.html', show_otp=True, email=email)

    success, message = OTPService.verify_otp(email, otp, 'reset')

    if success:
        try:
            user = User.query.filter_by(email=email).first()
            if not user:
                flash('User not found.', 'error')
                return redirect(url_for('auth.forgot_password'))

            user.set_password(new_password)
            db.session.commit()

            session.pop('password_reset_email', None)

            # ── ✅ Email: Password reset success confirmation ──────────────────
            try:
                from app.utils.email import send_password_reset_success
                send_password_reset_success(user)
            except Exception as e:
                current_app.logger.warning(f"Password reset success email failed: {e}")

            # Activity log
            try:
                from app.utils.firestore_sync import log_activity
                log_activity(
                    activity_type='password_reset',
                    user_id=user.id,
                    user_name=user.name,
                    details=f"{user.name} reset their password via OTP",
                    metadata={'email': email}
                )
            except Exception as e:
                current_app.logger.warning(f"Password reset activity log failed: {e}")

            flash('Password reset successful! Please login with your new password.', 'success')
            return redirect(url_for('auth.login'))

        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Password reset failed: {e}")
            flash(f'Password reset failed: {str(e)}', 'error')
            return render_template('auth/forgot_password.html', show_otp=True, email=email)

    flash(message, 'error')
    return render_template('auth/forgot_password.html', show_otp=True, email=email)


# ── Resend OTP for password reset ─────────────────────────────────────────────

@auth_bp.route('/resend-password-otp', methods=['POST'])
def resend_password_otp():
    if 'password_reset_email' not in session:
        return jsonify({'success': False, 'message': 'No password reset request found'}), 400

    email = session['password_reset_email']
    success, message = OTPService.send_otp(email, 'reset')
    return jsonify({'success': success, 'message': message})
