"""
Fallback entrypoint for OKXStatBot API.
Render and other platforms look for this file.
"""

import sys
from pathlib import Path

# Ensure imports work regardless of how the module is loaded
sys.path.insert(0, str(Path(__file__).parent))

from app.main import app

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8081, log_level="info")
