from app.models import User
from app.extensions import db
from flask import current_app
from app.firebase.admin_auth import FirebaseAuthService


class AuthService:
    """Authentication business logic"""
    
    @staticmethod
    def register_user(email, password, name, role='participant', phone=None):
        """Register a new user"""
        try:
            # Check if user already exists
            if User.query.filter_by(email=email).first():
                return None, "Email already registered"
            
            # Create Firebase user (optional - can be skipped if Firebase not configured)
            firebase_uid = None
            try:
                firebase_uid = FirebaseAuthService.create_user(email, password, name)
            except:
                current_app.logger.warning("Firebase user creation skipped")
            
            # Create user in database
            user = User(
                email=email,
                name=name,
                role=role,
                phone=phone,
                firebase_uid=firebase_uid
            )
            user.set_password(password)
            
            db.session.add(user)
            db.session.commit()
            
            current_app.logger.info(f"User registered: {email}")
            return user, None
            
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Registration failed: {str(e)}")
            return None, "Registration failed. Please try again."
    
    @staticmethod
    def verify_credentials(email, password):
        """Verify user login credentials"""
        user = User.query.filter_by(email=email).first()
        
        if user and user.check_password(password) and user.is_active:
            current_app.logger.info(f"Login successful: {email}")
            return user
        
        current_app.logger.warning(f"Login failed: {email}")
        return None
    
    @staticmethod
    def email_exists(email):
        """Check if email is already registered"""
        return User.query.filter_by(email=email).first() is not None
    
    @staticmethod
    def get_user_by_id(user_id):
        """Get user by ID"""
        return User.query.get(user_id)
    
    @staticmethod
    def update_user_profile(user_id, **kwargs):
        """Update user profile"""
        try:
            user = User.query.get(user_id)
            if not user:
                return False, "User not found"
            
            for key, value in kwargs.items():
                if hasattr(user, key) and key != 'password_hash':
                    setattr(user, key, value)
            
            db.session.commit()
            current_app.logger.info(f"User profile updated: {user_id}")
            return True, "Profile updated successfully"
            
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Profile update failed: {str(e)}")
            return False, "Update failed"
    
    @staticmethod
    def change_password(user_id, old_password, new_password):
        """Change user password"""
        try:
            user = User.query.get(user_id)
            if not user:
                return False, "User not found"
            
            if not user.check_password(old_password):
                return False, "Incorrect current password"
            
            user.set_password(new_password)
            db.session.commit()
            
            current_app.logger.info(f"Password changed: {user_id}")
            return True, "Password changed successfully"
            
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Password change failed: {str(e)}")
            return False, "Password change failed"
