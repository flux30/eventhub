# scripts/test_stats.py
# Run from project root: python scripts/test_stats.py

import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import create_app
from app.models import User
from app.services.event_service import EventService
from dotenv import load_dotenv
load_dotenv()

app = create_app('development')

with app.app_context():
    print("\n=== Organizer Stats Test ===")

    organizer = User.query.filter_by(role='organizer').first()
    if not organizer:
        print("❌ No organizer found.")
        sys.exit(1)

    stats = EventService.get_organizer_stats(organizer.id)

    print(f"\n{'Key':<30} {'Value'}")
    print("-" * 50)
    for k, v in stats.items():
        print(f"{k:<30} {v}")

    # Sanity checks
    assert stats['total_events'] is not None,           "❌ total_events is None"
    assert stats['total_revenue'] is not None,          "❌ total_revenue is None"
    assert isinstance(stats['total_events'], int),      "❌ total_events not an int"
    assert isinstance(stats['total_revenue'], float),   "❌ total_revenue not a float"
    assert stats['attendance_rate'] <= 100.0,           "❌ attendance_rate > 100%"

    print("\n✅ Stats sanity checks passed.")
