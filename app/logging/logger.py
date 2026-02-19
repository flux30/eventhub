import logging
from logging.handlers import RotatingFileHandler
import os


def setup_logging(app):
    """Setup logging configuration"""
    
    # Create logs directory if it doesn't exist
    if not os.path.exists('logs'):
        os.mkdir('logs')
    
    # Application log file
    app_handler = RotatingFileHandler(
        'logs/app.log',
        maxBytes=10240000,  # 10MB
        backupCount=3
    )
    app_handler.setFormatter(logging.Formatter(
        '[%(asctime)s] %(levelname)s in %(module)s: %(message)s'
    ))
    app_handler.setLevel(logging.INFO)
    
    # Error log file
    error_handler = RotatingFileHandler(
        'logs/error.log',
        maxBytes=10240000,
        backupCount=3
    )
    error_handler.setFormatter(logging.Formatter(
        '[%(asctime)s] %(levelname)s in %(module)s: %(message)s\n'
        'Path: %(pathname)s:%(lineno)d\n'
    ))
    error_handler.setLevel(logging.ERROR)
    
    # Add handlers to app logger
    app.logger.addHandler(app_handler)
    app.logger.addHandler(error_handler)
    app.logger.setLevel(logging.INFO)
    
    # Console output in development
    if app.debug:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.DEBUG)
        console_handler.setFormatter(logging.Formatter(
            '%(levelname)s: %(message)s'
        ))
        app.logger.addHandler(console_handler)
    
    app.logger.info('Event Management System started')
