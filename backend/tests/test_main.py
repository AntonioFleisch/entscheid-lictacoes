import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

def test_echo_dict():
    payload = {"message": "Hello", "foo": "bar"}
    response = client.post("/echo", json=payload)
    assert response.status_code == 200
    assert response.json() == payload

def test_echo_list():
    payload = [1, 2, "three"]
    response = client.post("/echo", json=payload)
    assert response.status_code == 200
    assert response.json() == payload

def test_echo_string():
    payload = "Just a string"
    response = client.post("/echo", json=payload)
    assert response.status_code == 200
    assert response.json() == payload

def test_echo_int():
    payload = 12345
    response = client.post("/echo", json=payload)
    assert response.status_code == 200
    assert response.json() == payload
