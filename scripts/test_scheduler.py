# scripts/test_scheduler.py
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import create_app
from app.extensions import scheduler
from app.models import Event
from app.services.reminder_service import (
    schedule_event_reminder,
    cancel_event_reminder,
    get_reminder_status,
    _make_job_id
)
from datetime import datetime
from dotenv import load_dotenv
load_dotenv()

app = create_app('development')

with app.app_context():
    print("\n=== Scheduler Status ===")
    # NOTE: scheduler.running = False here is CORRECT and EXPECTED.
    # The scheduler only runs inside the `flask run` server process.
    # In this script, scheduler.app is set (via init_app) so job store
    # operations (add/remove/query) all work via SQLite without needing
    # the scheduler to be running.
    print(f"scheduler.running : {scheduler.running}  ← False is expected in scripts")
    print(f"scheduler.app     : {scheduler.app}")

    print("\n=== Job Test ===")
    event = Event.query.filter(Event.event_date > datetime.utcnow()).first()

    if not event:
        print("❌ No future events found. Create one via the UI first.")
        sys.exit(1)

    print(f"Using event : [{event.id}] {event.title}")
    print(f"Event date  : {event.event_date}")

    # ── Schedule ───────────────────────────────────────────────────────────────
    result = schedule_event_reminder(event)
    print(f"\nschedule_event_reminder()  → {result}")

    # Verify job exists in store (works even when scheduler is not running)
    job = scheduler.get_job(_make_job_id(event.id))
    job_in_store = job is not None
    print(f"Job in SQLite store        → {job_in_store}")
    print(f"Job ID                     → {job.id if job else 'N/A'}")

    status = get_reminder_status(event.id)
    print(f"get_reminder_status()      → {status}")

    jobs = scheduler.get_jobs()
    print(f"scheduler.get_jobs()       → {[j.id for j in jobs]}")

    # ── Cancel ─────────────────────────────────────────────────────────────────
    cancel_event_reminder(event.id)
    job_after = scheduler.get_job(_make_job_id(event.id))
    print(f"\nAfter cancel:")
    print(f"Job in SQLite store        → {job_after is not None}")
    print(f"get_reminder_status()      → {get_reminder_status(event.id)}")

    # ── Assertions ─────────────────────────────────────────────────────────────
    assert result is True,          "❌ schedule returned False"
    assert job_in_store is True,    "❌ job not found in store after scheduling"
    assert job_after is None,       "❌ cancel did not remove job from store"

    print("\n✅ All scheduler checks passed.")
    print("   (The scheduler will pick up these jobs when `flask run` starts.)")
