import time
from fastapi.testclient import TestClient

from main import app


def test_create_and_get_prediction():
    # Use TestClient as context manager so startup/shutdown events run
    with TestClient(app) as client:
        # allow startup to complete
        time.sleep(0.1)

        payload = {
            "location_id": "test-loc-1",
            "prediction_type": "severity",
            "features": {
                "temperature": 26,
                "humidity": 60,
                "wind_speed": 5,
                "pressure": 1012,
            },
        }

        res = client.post("/api/predictions", json=payload)
        assert res.status_code == 201, res.text
        data = res.json()
        assert data["location_id"] == payload["location_id"]
        assert "id" in data

        # retrieve via list endpoint
        res2 = client.get("/api/predictions", params={"location_id": payload["location_id"]})
        # TestClient follows redirects by default; expect 200
        assert res2.status_code == 200, res2.text
        items = res2.json()
        assert isinstance(items, list)
        assert any(item.get("id") == data["id"] for item in items)
