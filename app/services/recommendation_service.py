from app.models import Event, Registration, User, Feedback
from app.extensions import db
from datetime import datetime
from sqlalchemy import func


class RecommendationService:
    """Service for event recommendations"""
    
    @staticmethod
    def get_recommendations(user_id, limit=10):
        """Get personalized event recommendations for a user"""
        user = User.query.get(user_id)
        if not user:
            return []
        
        # Get user's past registrations
        past_registrations = Registration.query.filter_by(user_id=user_id).all()
        past_event_ids = [reg.event_id for reg in past_registrations]
        
        # Get categories user has attended
        attended_categories = db.session.query(Event.category).join(Registration).filter(
            Registration.user_id == user_id
        ).distinct().all()
        attended_categories = [cat[0] for cat in attended_categories]
        
        # Get upcoming events in preferred categories
        recommended_events = Event.query.filter(
            Event.event_date > datetime.utcnow(),
            Event.is_active == True,
            Event.id.notin_(past_event_ids)
        ).order_by(Event.event_date).limit(limit * 2).all()
        
        # Score events
        scored_events = []
        for event in recommended_events:
            score = 0
            
            # Category match
            if event.category in attended_categories:
                score += 10
            
            # Popular events (high registration)
            registrations = Registration.query.filter_by(event_id=event.id).count()
            if registrations > 20:
                score += 5
            
            # Highly rated events
            avg_rating = db.session.query(func.avg(Feedback.rating)).filter(
                Feedback.event_id == event.id
            ).scalar()
            if avg_rating and avg_rating >= 4:
                score += 3
            
            # Free events
            if not event.is_paid:
                score += 2
            
            # Available seats
            if event.available_seats > 10:
                score += 1
            
            scored_events.append((event, score))
        
        # Sort by score and return
        scored_events.sort(key=lambda x: x[1], reverse=True)
        return [event for event, score in scored_events[:limit]]
    
    @staticmethod
    def get_similar_events(event_id, limit=5):
        """Get events similar to a given event"""
        event = Event.query.get(event_id)
        if not event:
            return []
        
        # Find events in same category
        similar_events = Event.query.filter(
            Event.category == event.category,
            Event.id != event_id,
            Event.is_active == True,
            Event.event_date > datetime.utcnow()
        ).order_by(Event.event_date).limit(limit).all()
        
        return similar_events
    
    @staticmethod
    def get_popular_events(limit=10):
        """Get popular events based on registrations"""
        popular_events = db.session.query(
            Event,
            func.count(Registration.id).label('registration_count')
        ).join(Registration).filter(
            Event.is_active == True,
            Event.event_date > datetime.utcnow()
        ).group_by(Event.id).order_by(
            func.count(Registration.id).desc()
        ).limit(limit).all()
        
        return [event for event, count in popular_events]
