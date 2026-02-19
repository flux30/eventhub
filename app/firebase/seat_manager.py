from firebase_admin import firestore
import firebase_admin


class SeatManager:
    """Manage event seats with Firebase for real-time sync"""
    
    def __init__(self):
        try:
            self.db = firestore.client()
        except:
            firebase_admin.initialize_app()
            self.db = firestore.client()
    
    def initialize_event_seats(self, event_id, total_seats):
        """Initialize seat count for new event"""
        try:
            self.db.collection('event_seats').document(str(event_id)).set({
                'available_seats': total_seats,
                'total_seats': total_seats,
                'last_updated': firestore.SERVER_TIMESTAMP
            })
            return True
        except Exception as e:
            print(f"Failed to initialize seats: {e}")
            return False
    
    def get_available_seats(self, event_id):
        """Get real-time available seats"""
        try:
            doc = self.db.collection('event_seats').document(str(event_id)).get()
            if doc.exists:
                return doc.to_dict()['available_seats']
            return None
        except Exception as e:
            print(f"Failed to get seats: {e}")
            return None
    
    @firestore.transactional
    def reserve_seat(self, transaction, event_id):
        """Atomically reserve a seat (prevents race conditions)"""
        seat_ref = self.db.collection('event_seats').document(str(event_id))
        snapshot = seat_ref.get(transaction=transaction)
        
        if not snapshot.exists:
            raise ValueError("Event not found")
        
        current_seats = snapshot.to_dict()['available_seats']
        
        if current_seats <= 0:
            raise ValueError("No seats available")
        
        transaction.update(seat_ref, {
            'available_seats': current_seats - 1,
            'last_updated': firestore.SERVER_TIMESTAMP
        })
        
        return current_seats - 1
    
    def release_seat(self, event_id):
        """Release a seat (when registration cancelled)"""
        try:
            seat_ref = self.db.collection('event_seats').document(str(event_id))
            seat_ref.update({
                'available_seats': firestore.Increment(1),
                'last_updated': firestore.SERVER_TIMESTAMP
            })
            return True
        except Exception as e:
            print(f"Failed to release seat: {e}")
            return False


seat_manager = SeatManager()
