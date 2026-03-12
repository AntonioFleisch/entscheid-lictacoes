
import os
import sys
import uuid
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient
from main import app

import main

client = TestClient(app)

def setup_env():
    os.environ["ADMIN_API_KEY"] = "test-key"
    main.get_admin_api_key = lambda: "test-key"

def test_ingest_watch():
    setup_env()
    tid = f"T-WATCH-{uuid.uuid4().hex[:6]}"
    
    # action default (watch) or explicit watch
    response = client.post(
        "/ingest/workflow-items",
        headers={"X-API-Key": "test-key"},
        json={"tender_id": tid, "action": "watch"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "watching"
    assert data["tender_id"] == tid

def test_ingest_participate():
    setup_env()
    tid = f"T-PART-{uuid.uuid4().hex[:6]}"
    
    response = client.post(
        "/ingest/workflow-items",
        headers={"X-API-Key": "test-key"},
        json={"tender_id": tid, "action": "participate"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "participating"
    assert data["tender_id"] == tid

def test_ingest_discard():
    setup_env()
    tid = f"T-DISC-{uuid.uuid4().hex[:6]}"
    
    response = client.post(
        "/ingest/workflow-items",
        headers={"X-API-Key": "test-key"},
        json={"tender_id": tid, "action": "discard"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "discarded"
    assert data["tender_id"] == tid

def test_ingest_default_action():
    setup_env()
    tid = f"T-DEF-{uuid.uuid4().hex[:6]}"
    
    # Missing action -> default watch
    response = client.post(
        "/ingest/workflow-items",
        headers={"X-API-Key": "test-key"},
        json={"tender_id": tid}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "watching"

def test_ingest_idempotency_preserves_status():
    setup_env()
    tid = f"T-IDEM-{uuid.uuid4().hex[:6]}"
    idem_key = f"key-{uuid.uuid4()}"
    
    # 1. Create as participating
    res1 = client.post(
        "/ingest/workflow-items",
        headers={"X-API-Key": "test-key", "Idempotency-Key": idem_key},
        json={"tender_id": tid, "action": "participate"}
    )
    assert res1.status_code == 200
    assert res1.json()["status"] == "participating"
    
    # 2. Retry with different action (discard) but same key -> Should return ORIGINAL response (participating)
    res2 = client.post(
        "/ingest/workflow-items",
        headers={"X-API-Key": "test-key", "Idempotency-Key": idem_key},
        json={"tender_id": tid, "action": "discard"}
    )
    assert res2.status_code == 200
    assert res2.json()["status"] == "participating" # Preserved from first call
