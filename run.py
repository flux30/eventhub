# run.py — FULL CORRECTED FILE
from dotenv import load_dotenv
load_dotenv()   # ← Must be FIRST, before any Flask imports that read os.getenv()

from app import create_app, db
from app.models import User, Event, Registration, Feedback

app = create_app('development')   # ← Only ONE call


@app.shell_context_processor
def make_shell_context():
    """Make database models available in shell"""
    return {
        'db': db,
        'User': User,
        'Event': Event,
        'Registration': Registration,
        'Feedback': Feedback
    }


if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=5000)
