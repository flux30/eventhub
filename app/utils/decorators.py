from functools import wraps
from flask import redirect, url_for, flash, abort
from flask_login import current_user


def role_required(*roles):
    """Decorator to restrict access based on user role"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                flash('Please log in to access this page.', 'warning')
                return redirect(url_for('auth.login'))
            
            if current_user.role not in roles:
                flash('You do not have permission to access this page.', 'danger')
                abort(403)
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def admin_required(f):
    """Decorator for admin-only routes"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('auth.login'))
        
        if current_user.role != 'admin':
            flash('Admin access required.', 'danger')
            abort(403)
        
        return f(*args, **kwargs)
    return decorated_function


def organizer_required(f):
    """Decorator for organizer-only routes"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('auth.login'))
        
        if current_user.role not in ['admin', 'organizer']:
            flash('Organizer access required.', 'danger')
            abort(403)
        
        return f(*args, **kwargs)
    return decorated_function
