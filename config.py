# config.py
import os
from datetime import timedelta


class Config:
    SECRET_KEY                     = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')
    SQLALCHEMY_DATABASE_URI        = 'sqlite:///eventhub.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False


    # ── Email ──────────────────────────────────────────────────────────────────
    MAIL_SERVER         = os.getenv('MAIL_SERVER', 'smtp.gmail.com')
    MAIL_PORT           = int(os.getenv('MAIL_PORT', 587))
    MAIL_USE_TLS        = os.getenv('MAIL_USE_TLS', 'True') == 'True'
    MAIL_USERNAME       = os.getenv('MAIL_USERNAME')
    MAIL_PASSWORD       = os.getenv('MAIL_PASSWORD')
    MAIL_DEFAULT_SENDER = os.getenv('MAIL_DEFAULT_SENDER', 'noreply@eventhub.com')
    BASE_URL            = os.getenv('BASE_URL', 'http://127.0.0.1:5000')


    # ── Firebase ───────────────────────────────────────────────────────────────
    FIREBASE_API_KEY             = os.getenv('FIREBASE_API_KEY', '')
    FIREBASE_AUTH_DOMAIN         = os.getenv('FIREBASE_AUTH_DOMAIN', '')
    FIREBASE_PROJECT_ID          = os.getenv('FIREBASE_PROJECT_ID', '')
    FIREBASE_STORAGE_BUCKET      = os.getenv('FIREBASE_STORAGE_BUCKET', '')
    FIREBASE_MESSAGING_SENDER_ID = os.getenv('FIREBASE_MESSAGING_SENDER_ID', '')
    FIREBASE_APP_ID              = os.getenv('FIREBASE_APP_ID', '')

    FIREBASE_CREDENTIALS_PATH = os.getenv(
        'FIREBASE_CREDENTIALS_PATH',
        r'C:\Users\bijay\Documents\cc_project2\eventhub-421da-firebase-adminsdk-fbsvc-63f54782d8.json'
    )


    # ── Session & Uploads ──────────────────────────────────────────────────────
    PERMANENT_SESSION_LIFETIME = timedelta(days=7)
    UPLOAD_FOLDER              = 'app/static/uploads'
    MAX_CONTENT_LENGTH         = 16 * 1024 * 1024
    ALLOWED_EXTENSIONS         = {'png', 'jpg', 'jpeg', 'gif', 'webp'}


    # ── APScheduler ────────────────────────────────────────────────────────────
    SCHEDULER_API_ENABLED = False

    # Absolute path — avoids any working-directory ambiguity on Windows
    _BASE_DIR = os.path.abspath(os.path.dirname(__file__))
    SCHEDULER_JOBSTORES = {
        'default': {
            'type': 'sqlalchemy',
            'url': f"sqlite:///{os.path.join(_BASE_DIR, 'instance', 'eventhub.db')}"
        }
    }

    # ✅ SCHEDULER_EXECUTORS intentionally omitted.
    # APScheduler defaults to a threadpool executor automatically.
    # Specifying it explicitly causes a version-dependent ValueError:
    #   "Cannot create executor — either type or class must be defined"

    SCHEDULER_JOB_DEFAULTS = {
        'coalesce':           True,   # merge missed runs into one if server was down
        'max_instances':      1,      # prevent the same job running twice in parallel
        'misfire_grace_time': 7200    # fire up to 2 hrs late after a restart
    }


class DevelopmentConfig(Config):
    DEBUG   = True
    TESTING = False


class ProductionConfig(Config):
    DEBUG   = False
    TESTING = False


class TestingConfig(Config):
    TESTING                 = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///test_eventhub.db'

    # Memory store in tests — no SQLite file, no persistence needed
    SCHEDULER_JOBSTORES = {
        'default': {'type': 'memory'}
    }


config = {
    'development': DevelopmentConfig,
    'production':  ProductionConfig,
    'testing':     TestingConfig,
    'default':     DevelopmentConfig
}
