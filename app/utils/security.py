from flask import request, render_template, jsonify
from app.extensions import limiter


def rate_limit_error_handler(e):
    """Custom error handler for rate limit exceeded"""
    if request.path.startswith('/api/'):
        return jsonify({
            'error': 'Rate limit exceeded',
            'message': str(e.description)
        }), 429
    else:
        return render_template('errors/429.html'), 429


# Rate limiting decorators
def login_rate_limit():
    """Strict rate limit for login attempts"""
    return limiter.limit("5 per minute")


def api_rate_limit():
    """Standard API rate limit"""
    return limiter.limit("30 per minute")


def registration_rate_limit():
    """Moderate rate limit for registrations"""
    return limiter.limit("3 per minute")


def general_rate_limit():
    """General rate limit for forms"""
    return limiter.limit("10 per minute")
