"""
FastAPI application entry point for OKXStatBot API.
Used by deployment platforms like Render, Railway, etc.
"""

import sys
from pathlib import Path

# Ensure the app module can be imported
app_dir = Path(__file__).parent / "app"
if str(app_dir) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent))

from app.main import app as fastapi_app

app = fastapi_app

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8081, log_level="info")
