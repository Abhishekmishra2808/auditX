import sys
from pathlib import Path

# Add the parent directory to the Python path so we can import from app
sys.path.insert(0, str(Path(__file__).parent.parent))

from app import app

# Vercel expects the Flask app to be exported as 'app'
# No need for a custom handler, Vercel handles WSGI automatically
app = app