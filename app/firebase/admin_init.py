import firebase_admin
from firebase_admin import credentials, auth, storage, firestore
import os


class FirebaseAdmin:
    """Firebase Admin SDK singleton"""
    _instance = None
    _initialized = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(FirebaseAdmin, cls).__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not self._initialized:
            self._initialize_firebase()
            FirebaseAdmin._initialized = True
    
    def _initialize_firebase(self):
        """Initialize Firebase Admin SDK"""
        try:
            cred_path = os.environ.get('FIREBASE_CREDENTIALS', 'firebase-credentials.json')
            
            if os.path.exists(cred_path):
                cred = credentials.Certificate(cred_path)
                firebase_admin.initialize_app(cred, {
                    'storageBucket': os.environ.get('FIREBASE_STORAGE_BUCKET')
                })
                print("✓ Firebase Admin SDK initialized successfully")
            else:
                print("⚠ Firebase credentials file not found. Some features may not work.")
        except Exception as e:
            print(f"⚠ Firebase initialization failed: {str(e)}")
    
    @staticmethod
    def get_auth():
        """Get Firebase Auth instance"""
        return auth
    
    @staticmethod
    def get_storage():
        """Get Firebase Storage instance"""
        return storage.bucket()
    
    @staticmethod
    def get_firestore():
        """Get Firestore instance"""
        return firestore.client()


# Initialize Firebase on import
firebase_instance = FirebaseAdmin()
