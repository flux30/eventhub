# app/extensions.py
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_wtf.csrf import CSRFProtect
from flask_mail import Mail
from flask_apscheduler import APScheduler          # ← NEW


# Initialize extensions
db          = SQLAlchemy()
migrate     = Migrate()
login_manager = LoginManager()
csrf        = CSRFProtect()
mail        = Mail()
scheduler   = APScheduler()                        # ← NEW


# Rate limiter
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"],
    storage_uri="memory://"
)


# Login manager configuration
login_manager.login_view         = 'auth.login'
login_manager.login_message      = 'Please log in to access this page.'
login_manager.login_message_category = 'info'
