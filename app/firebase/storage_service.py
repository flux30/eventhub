from firebase_admin import storage
import firebase_admin
from datetime import timedelta
import uuid


class FirebaseStorageService:
    """Handle file uploads to Firebase Storage"""
    
    def __init__(self):
        try:
            firebase_admin.get_app()
        except ValueError:
            firebase_admin.initialize_app()
        
        self.bucket = storage.bucket()
    
    def upload_event_banner(self, file, event_id):
        """Upload event banner and return public URL"""
        try:
            # Generate unique filename
            ext = file.filename.rsplit('.', 1)[1].lower()
            filename = f"event_banners/{event_id}_{uuid.uuid4()}.{ext}"
            
            blob = self.bucket.blob(filename)
            blob.upload_from_file(file, content_type=file.content_type)
            
            # Make public
            blob.make_public()
            
            return blob.public_url
        except Exception as e:
            print(f"Upload failed: {e}")
            return None
    
    def upload_profile_picture(self, file, user_id):
        """Upload user profile picture"""
        try:
            ext = file.filename.rsplit('.', 1)[1].lower()
            filename = f"profile_pictures/{user_id}.{ext}"
            
            blob = self.bucket.blob(filename)
            blob.upload_from_file(file, content_type=file.content_type)
            blob.make_public()
            
            return blob.public_url
        except Exception as e:
            print(f"Upload failed: {e}")
            return None
    
    def delete_file(self, file_url):
        """Delete file from storage"""
        try:
            # Extract path from URL
            path = file_url.split(f"{self.bucket.name}/")[-1]
            blob = self.bucket.blob(path)
            blob.delete()
            return True
        except Exception as e:
            print(f"Delete failed: {e}")
            return False


storage_service = FirebaseStorageService()
