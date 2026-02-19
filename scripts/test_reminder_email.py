# scripts/test_reminder_email.py
import sys, os

# ── MUST be before any app import ─────────────────────────────────────────────
# Config reads os.getenv() at class-definition time inside create_app().
# If load_dotenv() runs after 'from app import create_app', all mail
# credentials are already read as None and Flask-Mail skips AUTH entirely.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from dotenv import load_dotenv
load_dotenv()    # ← loads cc_project2/.env before config is read
# ──────────────────────────────────────────────────────────────────────────────

from app import create_app
from app.models import Registration
from app.utils.email_sender import send_event_reminder

app = create_app('development')

with app.app_context():
    print("\n=== Email Reminder Test ===")

    # Quick sanity check — confirm credentials loaded
    mail_user   = app.config.get('MAIL_USERNAME')
    mail_sender = app.config.get('MAIL_DEFAULT_SENDER')
    print(f"MAIL_USERNAME       : {mail_user}")
    print(f"MAIL_DEFAULT_SENDER : {mail_sender}")

    if not mail_user:
        print("❌ MAIL_USERNAME is None — .env not loading correctly.")
        print("   Confirm cc_project2/.env exists and has MAIL_USERNAME set.")
        sys.exit(1)

    if mail_sender == 'noreply@eventhub.com':
        print("⚠️  MAIL_DEFAULT_SENDER is still the default placeholder.")
        print("   Set MAIL_DEFAULT_SENDER=your.gmail@gmail.com in .env")
        sys.exit(1)

    reg = Registration.query.filter_by(status='confirmed').first()

    if not reg:
        print("❌ No confirmed registrations found.")
        print("   → Register for an event as a participant first, then re-run.")
        sys.exit(1)

    event = reg.event
    user  = reg.user

    print(f"\nRecipient  : {user.email}")
    print(f"Event      : {event.title}")
    print(f"Event date : {event.event_date}")
    print(f"Sending from: {mail_sender}")
    print(f"Sending...")

    try:
        send_event_reminder(
            user_email=user.email,
            user_name=user.name,
            event_title=event.title,
            event_date=event.event_date,
            event=event,
            user=user,
            registration=reg,
            base_url=app.config.get('BASE_URL', 'http://localhost:5000'),
        )
        print("✅ Email dispatched to background thread.")
        print("   Check inbox in ~10 seconds.")

        import time; time.sleep(10)
        print("Done.")
    except Exception as e:
        print(f"❌ Email failed: {e}")
        raise
