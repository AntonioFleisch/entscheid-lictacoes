import json
import os
from pathlib import Path
from typing import Dict, Optional

BASE_DIR = Path(__file__).resolve().parent
IDEMPOTENCY_FILE = BASE_DIR / "idempotency.json"

# Scope: Email -> "Method:Path:Key" -> Response

def load_idempotency_data() -> Dict:
    file_path = Path(IDEMPOTENCY_FILE)
    if not file_path.exists():
        return {}
    try:
        with open(file_path, "r") as f:
            return json.load(f)
    except json.JSONDecodeError:
        return {}

def save_idempotency_data(data: Dict):
    file_path = Path(IDEMPOTENCY_FILE)
    tmp_file = file_path.with_suffix(".json.tmp")
    with open(tmp_file, "w") as f:
        json.dump(data, f, indent=4, default=str)
    os.replace(tmp_file, file_path)

def _get_scope_key(method: str, path: str, key: str) -> str:
    return f"{method}:{path}:{key}"

def get_saved_response(email: str, method: str, path: str, key: str) -> Optional[Dict]:
    data = load_idempotency_data()
    user_data = data.get(email, {})
    scope_key = _get_scope_key(method, path, key)
    return user_data.get(scope_key)

def save_response(email: str, method: str, path: str, key: str, response_data: Dict, request_hash: str = None):
    # Optional logic: check request_hash to detect REUSED key with diff body?
    # For now, just save.
    data = load_idempotency_data()
    user_data = data.get(email, {})
    
    scope_key = _get_scope_key(method, path, key)
    
    user_data[scope_key] = response_data
    # Store hash if we wanted to validate reuse, maybe inside response_data or separate structure
    
    data[email] = user_data
    save_idempotency_data(data)
