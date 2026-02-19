from firebase_admin import firestore
from datetime import datetime, timezone
import firebase_admin


class ActivityLogger:
    """Log activities to Firebase Firestore for real-time dashboard"""
    
    def __init__(self):
        try:
            self.db = firestore.client()
        except:
            firebase_admin.initialize_app()
            self.db = firestore.client()
    
    def log_activity(self, activity_type, user_id, user_name, details, metadata=None):
        """
        Log activity to Firestore
        
        Args:
            activity_type: 'registration', 'event_created', 'user_signup', etc.
            user_id: User ID
            user_name: User display name
            details: Human-readable description
            metadata: Additional data (event_id, etc.)
        """
        try:
            activity_ref = self.db.collection('activities')
            activity_data = {
                'type': activity_type,
                'user_id': user_id,
                'user_name': user_name,
                'details': details,
                'timestamp': firestore.SERVER_TIMESTAMP,
                'metadata': metadata or {},
                'read': False  # For notification system
            }
            activity_ref.add(activity_data)
            return True
        except Exception as e:
            print(f"Activity logging failed: {e}")
            return False
    
    def get_recent_activities(self, limit=20):
        """Get recent activities for dashboard"""
        try:
            activities = (
                self.db.collection('activities')
                .order_by('timestamp', direction=firestore.Query.DESCENDING)
                .limit(limit)
                .stream()
            )
            
            result = []
            for doc in activities:
                data = doc.to_dict()
                data['id'] = doc.id
                result.append(data)
            return result
        except Exception as e:
            print(f"Failed to fetch activities: {e}")
            return []
    
    def get_activities_by_type(self, activity_type, limit=10):
        """Get activities filtered by type"""
        try:
            activities = (
                self.db.collection('activities')
                .where('type', '==', activity_type)
                .order_by('timestamp', direction=firestore.Query.DESCENDING)
                .limit(limit)
                .stream()
            )
            
            result = []
            for doc in activities:
                data = doc.to_dict()
                data['id'] = doc.id
                result.append(data)
            return result
        except Exception as e:
            print(f"Failed to fetch activities: {e}")
            return []


# Usage in your routes
activity_logger = ActivityLogger()
