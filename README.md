# EventHub — Event Management Platform
Python • Flask • SQLAlchemy • SQLite • Firebase Firestore • HTML/CSS/JS

EventHub is a full-stack event management web application built for a university submission and published as a public portfolio project. It supports role-based workflows and real-time seat availability updates using Firebase Firestore.

## Highlights
- Role-based access: Admin, Organizer, Participant
- Event lifecycle management: create, edit, publish, cancel, postpone (as implemented)
- Registrations, capacity tracking, and optional waitlist
- Real-time seat updates with Firestore listeners (no manual refresh)
- QR code ticketing and attendance verification
- Email/OTP flows and notifications (based on environment configuration)

## Technology
- Backend: Python, Flask
- Persistence: SQLite (development), SQLAlchemy ORM, Alembic migrations
- Real-time: Firebase Firestore (client listener) and Firebase Admin SDK (server operations)
- Frontend: Jinja2 templates, Vanilla JavaScript, CSS

## Quick Start
1. Clone:
   - `git clone https://github.com/flux30/eventhub.git`
   - `cd eventhub`

2. Create and activate a virtual environment:
   - Windows (PowerShell): `python -m venv venv` then `venv\Scripts\Activate.ps1`
   - macOS/Linux: `python3 -m venv venv` then `source venv/bin/activate`

3. Install dependencies:
   - `pip install -r requirements.txt`

4. Configure environment:
   - Copy `.env.example` → `.env` and fill in required values.

5. Add Firebase Admin credentials (local only):
   - Place your service account JSON (example: `firebase-credentials.json`)
   - Ensure it is not committed to Git.

6. Run migrations:
   - `flask db upgrade`

7. Start the app:
   - `python run.py`
   - Open `http://127.0.0.1:5000`

## Security Notes
- Do not commit secrets: `.env`, service account JSON, API keys, or local database files.
- Treat uploads and generated artifacts as runtime data.

## Portfolio Context
This repository is published for demonstration and evaluation. If you reuse the code, review and update configuration, security rules, and credentials for your own environment.
