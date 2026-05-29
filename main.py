"""Task-pilot entry point.

Run with:
    uvicorn main:app --reload --port 8000
"""

from src.app import create_app

app = create_app()
