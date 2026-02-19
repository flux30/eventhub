from firebase_admin import storage
from flask import current_app
import uuid
from datetime import timedelta


class FirebaseStorageService:
    """Firebase Cloud Storage operations"""
    
    @staticmethod
    def upload_file(file, folder='uploads'):
        """
        Upload file to Firebase Storage
        Returns: Public URL of uploaded file
        """
        try:
            bucket = storage.bucket()
            
            # Generate unique filename
            filename = f"{folder}/{uuid.uuid4()}_{file.filename}"
            blob = bucket.blob(filename)
            
            # Upload file
            blob.upload_from_string(
                file.read(),
                content_type=file.content_type
            )
            
            # Make public
            blob.make_public()
            
            current_app.logger.info(f"File uploaded to Firebase Storage: {filename}")
            return blob.public_url
            
        except Exception as e:
            current_app.logger.error(f"File upload failed: {str(e)}")
            return None
    
    @staticmethod
    def delete_file(file_url):
        """Delete file from Firebase Storage"""
        try:
            # Extract blob name from URL
            bucket = storage.bucket()
            blob_name = file_url.split('/')[-1]
            blob = bucket.blob(blob_name)
            blob.delete()
            
            current_app.logger.info(f"File deleted from Firebase Storage: {blob_name}")
            return True
        except Exception as e:
            current_app.logger.error(f"File deletion failed: {str(e)}")
            return False
    
    @staticmethod
    def get_signed_url(file_path, expiration_minutes=60):
        """Generate signed URL for private file access"""
        try:
            bucket = storage.bucket()
            blob = bucket.blob(file_path)
            url = blob.generate_signed_url(
                expiration=timedelta(minutes=expiration_minutes)
            )
            return url
        except Exception as e:
            current_app.logger.error(f"Signed URL generation failed: {str(e)}")
            return None
