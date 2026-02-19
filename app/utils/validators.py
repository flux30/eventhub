import re
from flask import current_app


def validate_email(email):
    """Validate email format"""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None


def validate_phone(phone):
    """Validate phone number (Indian format)"""
    pattern = r'^[6-9]\d{9}$'
    return re.match(pattern, phone) is not None


def validate_password(password):
    """
    Validate password strength
    - At least 8 characters
    - Contains letter and number
    """
    if len(password) < 8:
        return False, "Password must be at least 8 characters long"
    
    if not re.search(r'[A-Za-z]', password):
        return False, "Password must contain at least one letter"
    
    if not re.search(r'\d', password):
        return False, "Password must contain at least one number"
    
    return True, "Valid password"


def allowed_file(filename):
    """Check if file extension is allowed"""
    ALLOWED_EXTENSIONS = current_app.config.get('ALLOWED_EXTENSIONS', {'png', 'jpg', 'jpeg', 'gif', 'pdf'})
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def sanitize_filename(filename):
    """Remove dangerous characters from filename"""
    filename = re.sub(r'[^\w\s.-]', '', filename)
    filename = filename.replace(' ', '_')
    return filename
