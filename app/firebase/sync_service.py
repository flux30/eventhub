from firebase_admin import firestore
import firebase_admin
from flask import current_app
from app.models import Event, Registration
from datetime import datetime


class FirebaseSync:
    """
    Sync service to keep Firestore in sync with SQLite
    SQLite is ALWAYS the source of truth
    Firestore is read-only mirror for real-time updates
    """
    
    def __init__(self):
        self.db = None
        self.enabled = False
        self._initialized = False
    
    def _ensure_initialized(self):
        """Lazy initialization - only initialize when first used"""
        if self._initialized:
            return
        
        try:
            if not firebase_admin._apps:
                # Initialize Firebase if not already done
                cred_path = 'firebase-credentials.json'
                cred = firebase_admin.credentials.Certificate(cred_path)
                firebase_admin.initialize_app(cred)
            
            self.db = firestore.client()
            self.enabled = True
            self._initialized = True
            
            if current_app:
                current_app.logger.info("✅ Firebase Sync initialized")
        except Exception as e:
            self.enabled = False
            self._initialized = True
            if current_app:
                current_app.logger.warning(f"⚠️ Firebase not available (will use SQLite only): {e}")
    
    # ========================================
    # EVENT SYNC
    # ========================================
    
    def sync_event_created(self, event):
        """Sync newly created event to Firestore"""
        self._ensure_initialized()
        if not self.enabled:
            return False
        
        try:
            event_ref = self.db.collection('events').document(str(event.id))
            event_ref.set({
                'event_id': event.id,
                'title': event.title,
                'category': event.category,
                'available_seats': event.available_seats,
                'max_participants': event.max_participants,
                'status': 'active' if event.is_active else 'inactive',
                'event_date': event.event_date.isoformat(),
                'is_sold_out': event.available_seats == 0,
                'registration_count': 0,
                'attendance_count': 0,
                'last_updated': firestore.SERVER_TIMESTAMP
            })
            
            current_app.logger.info(f"✅ Event {event.id} synced to Firestore")
            return True
        except Exception as e:
            current_app.logger.error(f"❌ Firestore sync failed: {e}")
            return False
    
    def sync_event_updated(self, event):
        """Sync event updates to Firestore"""
        self._ensure_initialized()
        if not self.enabled:
            return False
        
        try:
            event_ref = self.db.collection('events').document(str(event.id))
            event_ref.update({
                'title': event.title,
                'category': event.category,
                'available_seats': event.available_seats,
                'status': 'active' if event.is_active else 'inactive',
                'is_sold_out': event.available_seats == 0,
                'last_updated': firestore.SERVER_TIMESTAMP
            })
            
            current_app.logger.info(f"✅ Event {event.id} updated in Firestore")
            return True
        except Exception as e:
            current_app.logger.error(f"❌ Firestore update failed: {e}")
            return False
    
    def sync_event_status(self, event_id, status, reason=None):
        """
        Sync real-time event status changes
        Status: 'active', 'sold_out', 'cancelled', 'completed', 'postponed'
        """
        self._ensure_initialized()
        if not self.enabled:
            return False
        
        try:
            event_ref = self.db.collection('events').document(str(event_id))
            update_data = {
                'status': status,
                'last_updated': firestore.SERVER_TIMESTAMP
            }
            
            if reason:
                update_data['status_reason'] = reason
            
            # Special handling for sold out
            if status == 'sold_out':
                update_data['is_sold_out'] = True
                update_data['sold_out_at'] = firestore.SERVER_TIMESTAMP
            
            event_ref.update(update_data)
            
            # Also log to activity feed
            self._log_status_change(event_id, status, reason)
            
            current_app.logger.info(f"✅ Event {event_id} status: {status}")
            return True
        except Exception as e:
            current_app.logger.error(f"❌ Status sync failed: {e}")
            return False
    
    def sync_event_deleted(self, event_id):
        """Remove event from Firestore when deleted"""
        self._ensure_initialized()
        if not self.enabled:
            return False
        
        try:
            self.db.collection('events').document(str(event_id)).delete()
            current_app.logger.info(f"✅ Event {event_id} deleted from Firestore")
            return True
        except Exception as e:
            current_app.logger.error(f"❌ Firestore delete failed: {e}")
            return False
    
    # ========================================
    # SEAT AVAILABILITY SYNC
    # ========================================
    
    def sync_seat_release(self, event_id, seats_to_release=1):
        """Sync seat release when registration cancelled"""
        self._ensure_initialized()
        if not self.enabled:
            return False
        
        try:
            event_ref = self.db.collection('events').document(str(event_id))
            event_ref.update({
                'available_seats': firestore.Increment(seats_to_release),
                'is_sold_out': False,
                'status': 'active',
                'last_updated': firestore.SERVER_TIMESTAMP
            })
            
            current_app.logger.info(f"✅ Seats released for event {event_id}")
            return True
        except Exception as e:
            current_app.logger.error(f"❌ Seat release failed: {e}")
            return False
    
    # ========================================
    # REGISTRATION SYNC
    # ========================================
    
    def sync_registration_created(self, registration):
        """Sync new registration to Firestore"""
        self._ensure_initialized()
        if not self.enabled:
            return False
        
        try:
            # Update event's registration count
            event_ref = self.db.collection('events').document(str(registration.event_id))
            event_ref.update({
                'registration_count': firestore.Increment(1),
                'last_registration': firestore.SERVER_TIMESTAMP
            })
            
            # Log activity
            try:
                from app.firebase.activity_logger import activity_logger
                activity_logger.log_activity(
                    activity_type='registration',
                    user_id=registration.user_id,
                    user_name=registration.user.name,
                    details=f"{registration.user.name} registered for {registration.event.title}",
                    metadata={
                        'event_id': registration.event_id,
                        'status': registration.status
                    }
                )
            except:
                pass
            
            return True
        except Exception as e:
            current_app.logger.error(f"❌ Registration sync failed: {e}")
            return False
    
    def sync_attendance_marked(self, registration):
        """Sync attendance update to Firestore"""
        self._ensure_initialized()
        if not self.enabled:
            return False
        
        try:
            event_ref = self.db.collection('events').document(str(registration.event_id))
            event_ref.update({
                'attendance_count': firestore.Increment(1),
                'last_attendance': firestore.SERVER_TIMESTAMP
            })
            
            return True
        except Exception as e:
            current_app.logger.error(f"❌ Attendance sync failed: {e}")
            return False
    
    # ========================================
    # CONSISTENCY HELPERS
    # ========================================
    
    def verify_consistency(self, event_id):
        """
        Verify that Firestore data matches SQLite
        If mismatch, SQLite wins and Firestore is corrected
        """
        self._ensure_initialized()
        if not self.enabled:
            return True
        
        try:
            # Get SQLite data (source of truth)
            event = Event.query.get(event_id)
            if not event:
                return False
            
            # Get Firestore data
            event_ref = self.db.collection('events').document(str(event_id))
            firestore_doc = event_ref.get()
            
            if not firestore_doc.exists:
                # Firestore missing - sync from SQLite
                self.sync_event_created(event)
                return True
            
            firestore_data = firestore_doc.to_dict()
            
            # Check for mismatches
            if firestore_data.get('available_seats') != event.available_seats:
                current_app.logger.warning(
                    f"⚠️ Seat mismatch for event {event_id}: "
                    f"SQLite={event.available_seats}, Firestore={firestore_data.get('available_seats')}"
                )
                # Fix Firestore to match SQLite
                self.sync_event_updated(event)
            
            return True
        except Exception as e:
            current_app.logger.error(f"❌ Consistency check failed: {e}")
            return False
    
    def full_sync_event(self, event_id):
        """Force full sync of event from SQLite to Firestore"""
        self._ensure_initialized()
        event = Event.query.get(event_id)
        if event:
            return self.sync_event_updated(event)
        return False
    
    # ========================================
    # PRIVATE HELPERS
    # ========================================
    
    def _log_status_change(self, event_id, status, reason):
        """Log status changes to activity feed"""
        try:
            event = Event.query.get(event_id)
            if not event:
                return
            
            status_messages = {
                'sold_out': f"Event '{event.title}' is now SOLD OUT!",
                'cancelled': f"Event '{event.title}' has been CANCELLED - {reason or 'No reason provided'}",
                'postponed': f"Event '{event.title}' has been POSTPONED - {reason or 'New date TBA'}",
                'completed': f"Event '{event.title}' has been completed",
                'active': f"Event '{event.title}' is now active"
            }
            
            message = status_messages.get(status, f"Event status changed to {status}")
            
            try:
                from app.firebase.activity_logger import activity_logger
                activity_logger.log_activity(
                    activity_type='event_status_change',
                    user_id=event.organizer_id,
                    user_name=event.organizer.name,
                    details=message,
                    metadata={
                        'event_id': event_id,
                        'new_status': status,
                        'reason': reason
                    }
                )
            except:
                pass
        except Exception as e:
            current_app.logger.error(f"❌ Status log failed: {e}")


# Global instance (lazy initialization)
firebase_sync = FirebaseSync()
