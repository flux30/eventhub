from datetime import datetime
from app.extensions import db, login_manager
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id             = db.Column(db.Integer, primary_key=True)
    name           = db.Column(db.String(100), nullable=False)
    email          = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash  = db.Column(db.String(200), nullable=False)
    role           = db.Column(db.String(20), default='participant')
    profile_image  = db.Column(db.String(200))
    phone          = db.Column(db.String(20))
    is_active      = db.Column(db.Boolean, default=True)
    email_verified = db.Column(db.Boolean, default=False)
    created_at     = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    organized_events = db.relationship('Event', back_populates='organizer', lazy='dynamic')
    registrations    = db.relationship('Registration', back_populates='user', lazy='dynamic')
    # activity_logs added via backref in ActivityLog model

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f'<User {self.email}>'


class Event(db.Model):
    __tablename__ = 'events'

    id                    = db.Column(db.Integer, primary_key=True)
    title                 = db.Column(db.String(200), nullable=False)
    description           = db.Column(db.Text, nullable=False)
    category              = db.Column(db.String(50), nullable=False)
    event_type            = db.Column(db.String(20), default='in-person')
    event_date            = db.Column(db.DateTime, nullable=False, index=True)
    location              = db.Column(db.String(200), nullable=False)
    meeting_link          = db.Column(db.String(500))
    max_participants      = db.Column(db.Integer, nullable=False)
    min_participants      = db.Column(db.Integer)
    available_seats       = db.Column(db.Integer, nullable=False)
    registration_deadline = db.Column(db.DateTime, nullable=False)
    is_paid               = db.Column(db.Boolean, default=False)
    price                 = db.Column(db.Numeric(10, 2), default=0.00)
    tags                  = db.Column(db.String(500))
    requirements          = db.Column(db.Text)
    duration              = db.Column(db.Float)
    image                 = db.Column(db.String(500))   # local disk filename
    banner_url            = db.Column(db.String(500))   # Firebase Storage URL (optional)
    send_reminders        = db.Column(db.Boolean, default=True)
    allow_waitlist        = db.Column(db.Boolean, default=False)
    is_public             = db.Column(db.Boolean, default=True)
    is_active             = db.Column(db.Boolean, default=True)
    organizer_id          = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at            = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at            = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    status         = db.Column(db.String(20), default='active', nullable=False)
    status_reason  = db.Column(db.Text,     nullable=True)
    postponed_to   = db.Column(db.DateTime, nullable=True)
    cancelled_at   = db.Column(db.DateTime, nullable=True)


    # Relationships
    organizer     = db.relationship('User', back_populates='organized_events')
    registrations = db.relationship(
        'Registration', back_populates='event',
        lazy='dynamic', cascade='all, delete-orphan'
    )

    @property
    def registered_count(self):
        return self.max_participants - self.available_seats

    @property
    def capacity_percentage(self):
        if self.max_participants <= 0:
            return 0
        return round((self.registered_count / self.max_participants) * 100, 1)

    def __repr__(self):
        return f'<Event {self.title}>'


class Registration(db.Model):
    __tablename__ = 'registrations'

    id             = db.Column(db.Integer, primary_key=True)
    user_id        = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    event_id       = db.Column(db.Integer, db.ForeignKey('events.id'), nullable=False)
    status         = db.Column(db.String(20), default='pending')
    # status values: pending | confirmed | cancelled | waitlist
    payment_status = db.Column(db.String(20), default='not_required')
    # payment_status values: not_required | pending | paid | refunded
    qr_code        = db.Column(db.String(500))   # filename only, e.g. qr_42.png
    attended       = db.Column(db.Boolean, default=False)
    attendance_time= db.Column(db.DateTime)
    created_at     = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    user  = db.relationship('User', back_populates='registrations')
    event = db.relationship('Event', back_populates='registrations')

    def __repr__(self):
        return f'<Registration User:{self.user_id} Event:{self.event_id} [{self.status}]>'


class Feedback(db.Model):
    __tablename__ = 'feedbacks'

    id         = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    event_id   = db.Column(db.Integer, db.ForeignKey('events.id'), nullable=False)
    rating     = db.Column(db.Integer, nullable=False)   # 1–5
    comment    = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint('user_id', 'event_id', name='unique_user_event_feedback'),
    )

    def __repr__(self):
        return f'<Feedback User:{self.user_id} Event:{self.event_id} Rating:{self.rating}>'


class EventTeam(db.Model):
    """Co-organizer team for an event."""
    __tablename__ = 'event_teams'

    id       = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey('events.id'), nullable=False)
    user_id  = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    role     = db.Column(db.String(50), default='member')
    added_at = db.Column(db.DateTime, default=datetime.utcnow)

    user  = db.relationship('User')
    event = db.relationship('Event')

    __table_args__ = (
        db.UniqueConstraint('event_id', 'user_id', name='unique_event_user_team'),
    )

    def __repr__(self):
        return f'<EventTeam Event:{self.event_id} User:{self.user_id}>'


class ActivityLog(db.Model):
    """
    SQLite fallback for Firebase activity logging.
    Populated automatically by firestore_sync.log_activity()
    whenever Firebase is unreachable.
    """
    __tablename__ = 'activity_log'

    id            = db.Column(db.Integer, primary_key=True)
    activity_type = db.Column(db.String(64), nullable=False)
    # ✅ FIX: was 'user.id' — correct FK target is 'users.id'
    user_id       = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    details       = db.Column(db.Text, nullable=True)
    metadata_json = db.Column(db.Text, default='{}')
    created_at    = db.Column(db.DateTime, default=datetime.utcnow)

    # backref adds .activity_logs to User automatically
    user = db.relationship('User', backref=db.backref('activity_logs', lazy='dynamic'))

    @property
    def time_ago(self):
        delta = datetime.utcnow() - self.created_at
        if delta.seconds < 60:
            return f"{delta.seconds}s ago"
        elif delta.seconds < 3600:
            return f"{delta.seconds // 60}m ago"
        elif delta.seconds < 86400:
            return f"{delta.seconds // 3600}h ago"
        return f"{delta.days}d ago"

    def __repr__(self):
        return f'<ActivityLog {self.activity_type} by user {self.user_id}>'


class EventTemplate(db.Model):
    """Reusable event configuration templates."""
    __tablename__ = 'event_templates'

    id               = db.Column(db.Integer, primary_key=True)
    user_id          = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    template_name    = db.Column(db.String(100), nullable=False)
    title            = db.Column(db.String(200))
    description      = db.Column(db.Text)
    category         = db.Column(db.String(50))
    location         = db.Column(db.String(200))
    max_participants = db.Column(db.Integer)
    is_paid          = db.Column(db.Boolean, default=False)
    price            = db.Column(db.Numeric(10, 2), default=0.00)
    created_at       = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User')

    def __repr__(self):
        return f'<EventTemplate {self.template_name}>'
