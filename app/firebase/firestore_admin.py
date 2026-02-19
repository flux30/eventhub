from firebase_admin import firestore
from flask import current_app
from datetime import datetime


class FirestoreService:
    """Firestore real-time database operations"""
    
    def __init__(self):
        self.db = firestore.client()
    
    def update_event_seats(self, event_id, available_seats):
        """Update real-time seat availability"""
        try:
            doc_ref = self.db.collection('events').document(str(event_id))
            doc_ref.set({
                'event_id': event_id,
                'available_seats': available_seats,
                'last_updated': datetime.utcnow()
            }, merge=True)
            
            current_app.logger.info(f"Firestore updated: Event {event_id} seats = {available_seats}")
            return True
        except Exception as e:
            current_app.logger.error(f"Firestore update failed: {str(e)}")
            return False
    
    def get_event_seats(self, event_id):
        """Get real-time seat availability"""
        try:
            doc_ref = self.db.collection('events').document(str(event_id))
            doc = doc_ref.get()
            
            if doc.exists:
                return doc.to_dict().get('available_seats')
            return None
        except Exception as e:
            current_app.logger.error(f"Firestore read failed: {str(e)}")
            return None
    
    def add_chat_message(self, event_id, user_id, user_name, message):
        """Add message to event chat"""
        try:
            doc_ref = self.db.collection('chats').document(str(event_id)).collection('messages').document()
            doc_ref.set({
                'user_id': user_id,
                'user_name': user_name,
                'message': message,
                'timestamp': firestore.SERVER_TIMESTAMP
            })
            return True
        except Exception as e:
            current_app.logger.error(f"Chat message failed: {str(e)}")
            return False
    
    def get_chat_messages(self, event_id, limit=50):
        """Get recent chat messages"""
        try:
            messages_ref = self.db.collection('chats').document(str(event_id)).collection('messages')
            messages = messages_ref.order_by('timestamp', direction=firestore.Query.DESCENDING).limit(limit).stream()
            
            return [msg.to_dict() for msg in messages]
        except Exception as e:
            current_app.logger.error(f"Chat fetch failed: {str(e)}")
            return []
