from flask import current_app, render_template
from flask_mail import Message
from app.extensions import mail
from threading import Thread


class NotificationService:
    """Service for sending notifications"""
    
    @staticmethod
    def send_async_email(app, msg):
        """Send email asynchronously"""
        with app.app_context():
            try:
                mail.send(msg)
            except Exception as e:
                current_app.logger.error(f"Failed to send email: {str(e)}")
    
    @staticmethod
    def send_email(to, subject, template, **kwargs):
        """Send email notification"""
        try:
            msg = Message(
                subject=subject,
                recipients=[to],
                html=render_template(template, **kwargs),
                sender=current_app.config.get('MAIL_DEFAULT_SENDER')
            )
            
            # Send asynchronously
            app = current_app._get_current_object()
            thread = Thread(target=NotificationService.send_async_email, args=(app, msg))
            thread.start()
            
            return True
        except Exception as e:
            current_app.logger.error(f"Email error: {str(e)}")
            return False
    
    @staticmethod
    def send_registration_confirmation(user, event, registration):
        """Send registration confirmation email"""
        return NotificationService.send_email(
            to=user.email,
            subject=f"Registration Confirmed - {event.title}",
            template='emails/registration_confirmation.html',
            user_name=user.name,
            event_title=event.title,
            event_date=event.event_date.strftime('%A, %d %B %Y'),
            event_time=event.event_date.strftime('%I:%M %p'),
            event_location=event.location,
            registration_id=f"REG-{registration.id}",
            qr_code_url=registration.qr_code,
            ticket_url=f"/participant/ticket/{registration.id}"
        )
    
    @staticmethod
    def send_event_reminder(user, event, registration):
        """Send event reminder email"""
        return NotificationService.send_email(
            to=user.email,
            subject=f"Reminder: {event.title} is tomorrow!",
            template='emails/event_reminder.html',
            user_name=user.name,
            event_title=event.title,
            event_date=event.event_date.strftime('%A, %d %B %Y'),
            event_time=event.event_date.strftime('%I:%M %p'),
            event_location=event.location
        )
    
    @staticmethod
    def send_cancellation_notification(user, event):
        """Send event cancellation notification"""
        return NotificationService.send_email(
            to=user.email,
            subject=f"Event Cancelled - {event.title}",
            template='emails/cancellation.html',
            user_name=user.name,
            event_title=event.title
        )
