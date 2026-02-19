from firebase_admin import messaging
import firebase_admin


class NotificationService:
    """Send push notifications via Firebase Cloud Messaging"""
    
    def __init__(self):
        try:
            firebase_admin.get_app()
        except ValueError:
            firebase_admin.initialize_app()
    
    def send_registration_confirmation(self, user_token, event_title, event_date):
        """Send push notification for successful registration"""
        try:
            message = messaging.Message(
                notification=messaging.Notification(
                    title='Registration Confirmed! 🎉',
                    body=f'You\'re registered for {event_title} on {event_date}',
                ),
                data={
                    'type': 'registration',
                    'event_title': event_title,
                    'event_date': event_date
                },
                token=user_token,
            )
            
            response = messaging.send(message)
            return True, response
        except Exception as e:
            print(f"Notification failed: {e}")
            return False, str(e)
    
    def send_event_reminder(self, user_tokens, event_title, time_until):
        """Send bulk reminder (1 hour before event)"""
        try:
            message = messaging.MulticastMessage(
                notification=messaging.Notification(
                    title=f'Event Starting Soon! ⏰',
                    body=f'{event_title} starts in {time_until}',
                ),
                tokens=user_tokens,
            )
            
            response = messaging.send_multicast(message)
            return True, f"Sent to {response.success_count} users"
        except Exception as e:
            print(f"Bulk notification failed: {e}")
            return False, str(e)


notification_service = NotificationService()
