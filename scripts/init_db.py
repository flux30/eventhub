from app import create_app
from app.extensions import db
from app.models import User
from dotenv import load_dotenv
load_dotenv()

app = create_app()

with app.app_context():
    # Create all tables
    db.create_all()
    
    # Create admin user if not exists
    admin = User.query.filter_by(email='admin@eventmanager.com').first()
    
    if not admin:
        admin = User(
            email='admin@eventmanager.com',
            name='System Administrator',
            role='admin',
            phone='9999999999'
        )
        admin.set_password('admin123')
        admin.is_active = True
        
        db.session.add(admin)
        db.session.commit()
        
        print("✓ Admin user created")
        print("  Email: admin@eventmanager.com")
        print("  Password: admin123")
    else:
        print("✓ Admin user already exists")
    
    print("\n✓ Database initialized successfully!")
