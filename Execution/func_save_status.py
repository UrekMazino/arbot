import json
from pathlib import Path

_STATE_DIR = Path(__file__).resolve().parent / "state"
_STATUS_FILE = _STATE_DIR / "status.json"


def save_status(dict):
    _STATE_DIR.mkdir(parents=True, exist_ok=True)
    with _STATUS_FILE.open("w", encoding="utf-8") as fp:
        json.dump(dict, fp, indent=4)
