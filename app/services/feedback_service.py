from app.models import Feedback, Event
from app.extensions import db
from sqlalchemy import func


class FeedbackService:
    """Service for feedback and ratings"""
    
    @staticmethod
    def create_feedback(user_id, event_id, rating, comment=None):
        """Create or update feedback"""
        # Check if feedback already exists
        feedback = Feedback.query.filter_by(
            user_id=user_id,
            event_id=event_id
        ).first()
        
        if feedback:
            feedback.rating = rating
            feedback.comment = comment
        else:
            feedback = Feedback(
                user_id=user_id,
                event_id=event_id,
                rating=rating,
                comment=comment
            )
            db.session.add(feedback)
        
        db.session.commit()
        return feedback
    
    @staticmethod
    def get_event_rating(event_id):
        """Get average rating for an event"""
        result = db.session.query(
            func.avg(Feedback.rating).label('average'),
            func.count(Feedback.id).label('count')
        ).filter(Feedback.event_id == event_id).first()
        
        return {
            'average': round(result.average, 1) if result.average else 0,
            'count': result.count
        }
    
    @staticmethod
    def get_event_feedbacks(event_id):
        """Get all feedbacks for an event"""
        return Feedback.query.filter_by(event_id=event_id).all()
    
    @staticmethod
    def get_user_feedback(user_id, event_id):
        """Get user's feedback for a specific event"""
        return Feedback.query.filter_by(
            user_id=user_id,
            event_id=event_id
        ).first()
    
    @staticmethod
    def delete_feedback(feedback_id):
        """Delete a feedback"""
        feedback = Feedback.query.get(feedback_id)
        if not feedback:
            return False
        
        db.session.delete(feedback)
        db.session.commit()
        return True
