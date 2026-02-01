from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


def test_get_atualizacao():
    response = client.get("/atualizacao/12345")
    assert response.status_code == 200
    data = response.json()
    assert data["autorizaFolha"] is True
    assert data["autorizaFiscal"] is True
    assert data["autorizaContabil"] is True
    
    from datetime import datetime
    # Check format Year.Month.Day.Hour:Minute:Second
    # Example: 2023.10.27.10:30:00
    # Allow for potentially small time diffs, but mainly check format parsing
    # We use the same format string as in the main.py
    dt = datetime.strptime(data["versaoFolha"], "%Y.%m.%d.%H:%M:%S")
    assert data["versaoFolha"] == data["versaoFiscal"] == data["versaoContabil"]

