"""
Root entrypoint for the OKXStatBot API.
This is required for deployment platforms like Render to find the FastAPI app.
"""

from app.main import app

__all__ = ["app"]
