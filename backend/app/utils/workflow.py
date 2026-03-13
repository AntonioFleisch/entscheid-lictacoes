import json
import os
import uuid
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List
from app.db.models import WorkflowStatus

BASE_DIR = Path(__file__).resolve().parent
WORKFLOW_FILE = BASE_DIR / "workflow.json"

# Exceptions for domain rules (code, message)
class WorkflowError(Exception):
    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message

def load_workflow_data() -> Dict:
    file_path = Path(WORKFLOW_FILE)
    if not file_path.exists():
        return {}
    try:
        with open(file_path, "r") as f:
            return json.load(f)
    except json.JSONDecodeError:
        return {}

def save_workflow_data(data: Dict):
    file_path = Path(WORKFLOW_FILE)
    tmp_file = file_path.with_suffix(".json.tmp")
    with open(tmp_file, "w") as f:
        json.dump(data, f, indent=4, default=str)
    os.replace(tmp_file, file_path)

def get_user_items(email: str) -> List[Dict]:
    data = load_workflow_data()
    return data.get(email, [])

def create_item(email: str, tender_id: str, status: WorkflowStatus = WorkflowStatus.watching) -> Dict:
    data = load_workflow_data()
    user_items = data.get(email, [])
    
    # Check duplicate tender_id
    if any(item["tender_id"] == tender_id for item in user_items):
        raise WorkflowError("DUPLICATE_TENDER", f"User already has a workflow item for tender {tender_id}")

    new_item = {
        "id": str(uuid.uuid4()),
        "user_email": email,
        "tender_id": tender_id,
        "status": status.value,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    
    user_items.append(new_item)
    data[email] = user_items
    save_workflow_data(data)
    return new_item

def valid_transition(current: str, target: str) -> bool:
    # Final states cannot transition
    if current in ["won", "lost", "discarded"]:
        return False
    
    # Cannot return to watching
    if target == "watching":
        return False
    
    # participating -> [won, lost, discarded] OK
    if current == "participating" and target in ["won", "lost", "discarded"]:
        return True

    # watching -> [participating, discarded] OK
    if current == "watching" and target in ["participating", "discarded"]:
        return True
    
    return False

def update_item_status(email: str, item_id: str, new_status: WorkflowStatus) -> Dict:
    data = load_workflow_data()
    user_items = data.get(email, [])
    
    # Find item
    item_index = -1
    for i, item in enumerate(user_items):
        if item["id"] == item_id:
            item_index = i
            break
            
    if item_index == -1:
        raise WorkflowError("NOT_FOUND", "Workflow item not found")
        
    item = user_items[item_index]
    current_status = item["status"]
    target_status = new_status.value
    
    # Logic: If status is same, do nothing or success? Usually idempotent is better.
    if current_status == target_status:
        return item # No change needed
    
    if not valid_transition(current_status, target_status):
        raise WorkflowError("INVALID_TRANSITION", f"Cannot transition from {current_status} to {target_status}")

    # Update
    item["status"] = target_status
    item["updated_at"] = datetime.now(timezone.utc).isoformat()
    
    user_items[item_index] = item
    data[email] = user_items
    save_workflow_data(data)
    return item
