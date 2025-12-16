from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_create_contact():
    response = client.post("/contacts/", json={"name": "Alice", "phone": "1234567890"})
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Alice"
    assert data["phone"] == "1234567890"
    assert "id" in data

def test_read_contacts():
    client.post("/contacts/", json={"name": "Alice", "phone": "1234567890"})
    response = client.get("/contacts/")
    assert response.status_code == 200
    assert len(response.json()) > 0

def test_read_contact():
    # Create a contact first
    create_response = client.post("/contacts/", json={"name": "Bob", "phone": "9876543210"})
    contact_id = create_response.json()["id"]
    
    response = client.get(f"/contacts/{contact_id}")
    assert response.status_code == 200
    assert response.json()["name"] == "Bob"

def test_update_contact():
    # Create
    create_response = client.post("/contacts/", json={"name": "Charlie", "phone": "555"})
    contact_id = create_response.json()["id"]
    
    # Update
    response = client.put(f"/contacts/{contact_id}", json={"name": "Charlie Updated", "phone": "555555"})
    assert response.status_code == 200
    assert response.json()["name"] == "Charlie Updated"
    
    # Verify update
    get_response = client.get(f"/contacts/{contact_id}")
    assert get_response.json()["name"] == "Charlie Updated"

def test_delete_contact():
    # Create
    create_response = client.post("/contacts/", json={"name": "Dave", "phone": "666"})
    contact_id = create_response.json()["id"]
    
    # Delete
    response = client.delete(f"/contacts/{contact_id}")
    assert response.status_code == 200
    
    # Verify delete
    get_response = client.get(f"/contacts/{contact_id}")
    assert get_response.status_code == 404
