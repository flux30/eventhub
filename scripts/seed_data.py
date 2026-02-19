from app import create_app
from app.extensions import db
from app.models import User, Event
from datetime import datetime, timedelta
import random
from dotenv import load_dotenv
load_dotenv()

app = create_app()

with app.app_context():
    print("Seeding sample data...\n")
    
    # Create sample users
    users_data = [
        {'email': 'organizer1@test.com', 'name': 'John Organizer', 'role': 'organizer', 'password': 'password123'},
        {'email': 'organizer2@test.com', 'name': 'Sarah Organizer', 'role': 'organizer', 'password': 'password123'},
        {'email': 'participant1@test.com', 'name': 'Mike Participant', 'role': 'participant', 'password': 'password123'},
        {'email': 'participant2@test.com', 'name': 'Emma Participant', 'role': 'participant', 'password': 'password123'},
    ]
    
    users = []
    for user_data in users_data:
        if not User.query.filter_by(email=user_data['email']).first():
            user = User(
                email=user_data['email'],
                name=user_data['name'],
                role=user_data['role']
            )
            user.set_password(user_data['password'])
            db.session.add(user)
            users.append(user)
            print(f"✓ Created user: {user_data['email']}")
    
    db.session.commit()
    
    # Create sample events
    organizers = User.query.filter_by(role='organizer').all()
    
    if organizers:
        categories = ['workshop', 'seminar', 'conference', 'cultural', 'sports']
        
        events_data = [
            {
                'title': 'Python Programming Workshop',
                'description': 'Learn Python from scratch with hands-on projects',
                'category': 'workshop',
                'location': 'Computer Lab, Building A'
            },
            {
                'title': 'Web Development Bootcamp',
                'description': 'Full-stack web development training',
                'category': 'workshop',
                'location': 'Online - Zoom'
            },
            {
                'title': 'AI and Machine Learning Seminar',
                'description': 'Introduction to AI and ML concepts',
                'category': 'seminar',
                'location': 'Auditorium, Main Building'
            },
            {
                'title': 'Cultural Fest 2026',
                'description': 'Annual cultural festival with music, dance, and drama',
                'category': 'cultural',
                'location': 'Open Ground'
            },
            {
                'title': 'Tech Conference 2026',
                'description': 'Latest trends in technology',
                'category': 'conference',
                'location': 'Convention Center'
            }
        ]
        
        for i, event_data in enumerate(events_data):
            if not Event.query.filter_by(title=event_data['title']).first():
                event_date = datetime.utcnow() + timedelta(days=random.randint(7, 60))
                reg_deadline = event_date - timedelta(days=2)
                
                event = Event(
                    title=event_data['title'],
                    description=event_data['description'],
                    category=event_data['category'],
                    location=event_data['location'],
                    event_date=event_date,
                    registration_deadline=reg_deadline,
                    max_participants=random.randint(50, 200),
                    available_seats=random.randint(30, 150),
                    organizer_id=organizers[i % len(organizers)].id,
                    is_paid=random.choice([True, False]),
                    price=random.choice([0, 100, 200, 500])
                )
                
                db.session.add(event)
                print(f"✓ Created event: {event_data['title']}")
        
        db.session.commit()
    
    print("\n✓ Sample data seeded successfully!")
    print("\nTest accounts:")
    print("  Organizer 1: organizer1@test.com / password123")
    print("  Organizer 2: organizer2@test.com / password123")
    print("  Participant 1: participant1@test.com / password123")
    print("  Participant 2: participant2@test.com / password123")
