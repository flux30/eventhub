from firebase_admin import auth
from flask import current_app


class FirebaseAuthService:
    """Firebase Authentication operations"""
    
    @staticmethod
    def verify_token(id_token):
        """Verify Firebase ID token"""
        try:
            decoded_token = auth.verify_id_token(id_token)
            return decoded_token
        except Exception as e:
            current_app.logger.error(f"Token verification failed: {str(e)}")
            return None
    
    @staticmethod
    def create_user(email, password, display_name):
        """Create user in Firebase Authentication"""
        try:
            user = auth.create_user(
                email=email,
                password=password,
                display_name=display_name
            )
            current_app.logger.info(f"Firebase user created: {user.uid}")
            return user.uid
        except Exception as e:
            current_app.logger.error(f"Firebase user creation failed: {str(e)}")
            return None
    
    @staticmethod
    def delete_user(uid):
        """Delete user from Firebase Authentication"""
        try:
            auth.delete_user(uid)
            current_app.logger.info(f"Firebase user deleted: {uid}")
            return True
        except Exception as e:
            current_app.logger.error(f"Firebase user deletion failed: {str(e)}")
            return False
    
    @staticmethod
    def update_user(uid, **kwargs):
        """Update Firebase user"""
        try:
            auth.update_user(uid, **kwargs)
            return True
        except Exception as e:
            current_app.logger.error(f"Firebase user update failed: {str(e)}")
            return False
