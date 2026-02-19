# app/__init__.py
import os
import sys

from flask import Flask, render_template, redirect, url_for
from flask_login import current_user

from config import config
from app.extensions import db, login_manager, mail, migrate, scheduler


def create_app(config_name='default'):
    """Application factory"""
    app = Flask(__name__)

    app.config.from_object(config[config_name])

    initialize_extensions(app)
    register_blueprints(app)
    register_error_handlers(app)
    register_context_processors(app)
    register_commands(app)

    with app.app_context():
        from app.models import (
            User, Event, Registration, Feedback,
            EventTeam, ActivityLog, EventTemplate
        )
        db.create_all()

    # ── Scheduler start ────────────────────────────────────────────────────────
    #
    # Guard logic (simpler and more reliable than sys.argv check on Windows):
    #
    #   DEBUG=False (production / flask run without debug):
    #     _is_reloader_parent = (False and ...) = False  →  START ✓
    #
    #   DEBUG=True, Werkzeug reloader PARENT process:
    #     WERKZEUG_RUN_MAIN is not set
    #     _is_reloader_parent = (True and True) = True   →  SKIP ✓ (prevents double-start)
    #
    #   DEBUG=True, Werkzeug reloader CHILD process (the actual worker):
    #     WERKZEUG_RUN_MAIN = 'true'
    #     _is_reloader_parent = (True and False) = False →  START ✓
    #
    #   flask shell / flask db / python scripts/ (all use DevelopmentConfig, DEBUG=True):
    #     WERKZEUG_RUN_MAIN is not set
    #     _is_reloader_parent = (True and True) = True   →  SKIP ✓
    #
    # NOTE: sys.argv-based detection was removed — it is unreliable on Windows
    # because the flask entry point path varies by environment (conda vs venv).
    #
    _is_reloader_parent = (
        app.debug and os.environ.get('WERKZEUG_RUN_MAIN') != 'true'
    )

    if not _is_reloader_parent and not scheduler.running:
        try:
            scheduler.start()
            # print() is intentional — app.logger goes to log FILE in non-debug
            # mode and is invisible in the terminal. print() always reaches stdout.
            print(
                f"[EventHub] ✅ APScheduler started"
                f" | store=SQLite"
                f" | debug={app.debug}"
                f" | jobs={len(scheduler.get_jobs())}"
            )
        except Exception as e:
            print(f"[EventHub] ⚠️  APScheduler failed to start: {e}")

    return app


def initialize_extensions(app):
    """Initialize Flask extensions"""
    db.init_app(app)
    login_manager.init_app(app)
    mail.init_app(app)
    migrate.init_app(app, db)
    scheduler.init_app(app)    # must come before scheduler.start()

    login_manager.login_view             = 'auth.login'
    login_manager.login_message          = 'Please log in to access this page.'
    login_manager.login_message_category = 'info'

    @login_manager.user_loader
    def load_user(user_id):
        from app.models import User
        return User.query.get(int(user_id))


def register_blueprints(app):
    from app.auth.routes        import auth_bp
    from app.participant.routes import participant_bp
    from app.organizer.routes   import organizer_bp
    from app.admin.routes       import admin_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(participant_bp)
    app.register_blueprint(organizer_bp)
    app.register_blueprint(admin_bp)

    @app.route('/')
    def index():
        if current_user.is_authenticated:
            if current_user.role == 'admin':
                return redirect(url_for('admin.dashboard'))
            elif current_user.role == 'organizer':
                return redirect(url_for('organizer.dashboard'))
            else:
                return redirect(url_for('participant.dashboard'))

        from app.models import Event
        from datetime import datetime

        featured_events = (
            Event.query
            .filter(Event.event_date > datetime.utcnow(), Event.is_active == True)
            .order_by(Event.event_date)
            .limit(6)
            .all()
        )
        return render_template('index.html', featured_events=featured_events)

    @app.route('/dashboard')
    def dashboard():
        if not current_user.is_authenticated:
            return redirect(url_for('auth.login'))
        if current_user.role == 'admin':
            return redirect(url_for('admin.dashboard'))
        elif current_user.role == 'organizer':
            return redirect(url_for('organizer.dashboard'))
        else:
            return redirect(url_for('participant.dashboard'))


def register_error_handlers(app):
    @app.errorhandler(404)
    def not_found_error(error):
        return render_template('errors/404.html'), 404

    @app.errorhandler(500)
    def internal_error(error):
        db.session.rollback()
        return render_template('errors/500.html'), 500

    @app.errorhandler(403)
    def forbidden_error(error):
        return render_template('errors/403.html'), 403

    @app.errorhandler(401)
    def unauthorized_error(error):
        return render_template('errors/401.html'), 401


def register_context_processors(app):
    @app.context_processor
    def utility_processor():
        from app.utils.helpers import format_datetime, truncate_text, get_time_ago
        return dict(
            format_datetime=format_datetime,
            truncate_text=truncate_text,
            get_time_ago=get_time_ago
        )

    @app.context_processor
    def inject_now():
        from datetime import datetime
        return {'now': datetime.utcnow()}


def register_commands(app):
    @app.cli.command()
    def init_db():
        """Initialize the database"""
        db.create_all()
        print("Database initialized!")

    @app.cli.command()
    def seed_db():
        """Seed the database with sample data"""
        from app.models import User, Event
        from werkzeug.security import generate_password_hash
        from datetime import datetime, timedelta

        admin = User(
            name='Admin User', email='admin@eventhub.com',
            password_hash=generate_password_hash('admin123'), role='admin'
        )
        db.session.add(admin)

        organizer = User(
            name='John Organizer', email='organizer@eventhub.com',
            password_hash=generate_password_hash('organizer123'),
            role='organizer', phone='9876543210'
        )
        db.session.add(organizer)

        participant = User(
            name='Jane Participant', email='participant@eventhub.com',
            password_hash=generate_password_hash('participant123'),
            role='participant', phone='9876543211'
        )
        db.session.add(participant)
        db.session.commit()

        categories = ['workshop', 'seminar', 'conference', 'cultural', 'sports', 'networking']
        for i in range(10):
            event = Event(
                title=f'Sample Event {i+1}',
                description=f'Sample description for event {i+1}.',
                category=categories[i % len(categories)],
                event_date=datetime.utcnow() + timedelta(days=i * 7 + 5),
                location=f'Venue {i+1}, Building A',
                max_participants=50 + (i * 10),
                available_seats=50 + (i * 10),
                registration_deadline=datetime.utcnow() + timedelta(days=i * 7 + 3),
                is_paid=i % 2 == 0,
                price=500.0 if i % 2 == 0 else 0,
                organizer_id=organizer.id,
                is_active=True
            )
            db.session.add(event)
        db.session.commit()
        print("Database seeded!")

    @app.cli.command()
    def reset_db():
        """Reset the database"""
        db.drop_all()
        db.create_all()
        print("Database reset!")

    @app.cli.command()
    def create_admin():
        """Create an admin user interactively"""
        from app.models import User
        from werkzeug.security import generate_password_hash
        import getpass

        email = input("Enter admin email: ")
        if User.query.filter_by(email=email).first():
            print(f"User {email} already exists!")
            return

        name     = input("Enter admin name: ")
        password = getpass.getpass("Enter password: ")
        if password != getpass.getpass("Confirm password: "):
            print("Passwords do not match!")
            return

        admin = User(
            name=name, email=email,
            password_hash=generate_password_hash(password),
            role='admin'
        )
        db.session.add(admin)
        db.session.commit()
        print(f"Admin created: {email}")
