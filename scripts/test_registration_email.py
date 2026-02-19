# scripts/test_registration_email.py
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from dotenv import load_dotenv
load_dotenv()

from app import create_app
from app.models import Registration
from app.utils.email_sender import (
    send_registration_confirmation,
    send_waitlist_confirmation,
    send_cancellation_confirmation,
)
import time

app = create_app('development')

with app.app_context():
    reg = Registration.query.filter_by(status='confirmed').first()
    if not reg:
        print("❌ No confirmed registrations found.")
        sys.exit(1)

    event = reg.event
    user  = reg.user

    print(f"\n=== Test 1: Registration Confirmation ===")
    print(f"To: {user.email} | Event: {event.title}")
    send_registration_confirmation(
        user_email=user.email,
        user_name=user.name,
        event_title=event.title,
        event_date=event.event_date,
        event=event,
        user=user,
        registration=reg,
    )
    print("✅ Dispatched — check inbox")
    time.sleep(5)

    print(f"\n=== Test 2: Waitlist Confirmation ===")
    send_waitlist_confirmation(
        user_email=user.email,
        user_name=user.name,
        event_title=event.title,
        event_date=event.event_date,
        event=event,
        user=user,
    )
    print("✅ Dispatched — check inbox")
    time.sleep(5)

    print(f"\n=== Test 3: Cancellation Confirmation ===")
    send_cancellation_confirmation(
        user_email=user.email,
        user_name=user.name,
        event_title=event.title,
        event_date=event.event_date,
        event=event,
        user=user,
    )
    print("✅ Dispatched — check inbox")
    time.sleep(5)

    print("\nAll 3 emails dispatched. Verify all 3 arrive in inbox.")
