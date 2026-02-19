import qrcode
import io
import base64
from datetime import datetime, timezone
from flask import current_app


def generate_qr_code(data):
    """Generate QR code from data"""
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(data)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white")
    
    # Convert to base64
    buffer = io.BytesIO()
    img.save(buffer, format='PNG')
    img_str = base64.b64encode(buffer.getvalue()).decode()
    
    return f"data:image/png;base64,{img_str}"


def allowed_file(filename):
    """Check if file extension is allowed"""
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def format_datetime(dt, format='%B %d, %Y at %I:%M %p'):
    """Format datetime for display (timezone-aware)"""
    if isinstance(dt, str):
        dt = datetime.fromisoformat(dt)
    
    # Ensure timezone-aware
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    
    return dt.strftime(format)


def get_time_ago(dt):
    """Get relative time string (timezone-aware)"""
    # Ensure timezone-aware datetime
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    
    now = datetime.now(timezone.utc)
    delta = now - dt
    
    if delta.days > 365:
        years = delta.days // 365
        return f"{years} year{'s' if years > 1 else ''} ago"
    elif delta.days > 30:
        months = delta.days // 30
        return f"{months} month{'s' if months > 1 else ''} ago"
    elif delta.days > 0:
        return f"{delta.days} day{'s' if delta.days > 1 else ''} ago"
    elif delta.seconds > 3600:
        hours = delta.seconds // 3600
        return f"{hours} hour{'s' if hours > 1 else ''} ago"
    elif delta.seconds > 60:
        minutes = delta.seconds // 60
        return f"{minutes} minute{'s' if minutes > 1 else ''} ago"
    else:
        return "Just now"


def truncate_text(text, length=100):
    """Truncate text with ellipsis"""
    if not text:
        return ""
    if len(text) <= length:
        return text
    return text[:length] + "..."


def calculate_age(birthdate):
    """Calculate age from birthdate"""
    today = datetime.today()
    return today.year - birthdate.year - ((today.month, today.day) < (birthdate.month, birthdate.day))


def generate_registration_id(event_id, user_id):
    """Generate unique registration ID"""
    timestamp = int(datetime.utcnow().timestamp())
    return f"REG-{event_id}-{user_id}-{timestamp}"


def validate_phone(phone):
    """Validate phone number"""
    if not phone:
        return True
    
    # Remove spaces and special characters
    phone = ''.join(filter(str.isdigit, phone))
    
    # Check if 10 digits
    return len(phone) == 10


def sanitize_filename(filename):
    """Sanitize filename for safe storage"""
    import re
    filename = re.sub(r'[^\w\s.-]', '', filename)
    filename = re.sub(r'[-\s]+', '-', filename)
    return filename.lower()
