import io

import numpy as np
import torch
from fastapi.testclient import TestClient
from PIL import Image

from app.inference import model as model_mod
from tests.test_engine import FakeModel


def _jpeg(color):
    buf = io.BytesIO()
    arr = np.full((500, 600, 3), (150, 90, 160), np.uint8)
    arr[50:450, 50:550] = color
    Image.fromarray(arr).save(buf, "JPEG")
    buf.seek(0)
    return buf


def test_upload_analyze_queue_review(monkeypatch):
    fake = (FakeModel(), torch.device("cpu"))
    monkeypatch.setattr(model_mod, "load_model", lambda: fake)
    monkeypatch.setattr("app.worker.load_model", lambda: fake)
    monkeypatch.setattr("app.main.load_model", lambda: fake)
    from app.main import app

    with TestClient(app) as client:
        low = client.post("/api/cases", data={"patient_ref": "P-LOW"},
                          files={"image": ("a.jpg", _jpeg((150, 90, 160)), "image/jpeg")})
        high = client.post("/api/cases", data={"patient_ref": "P-HIGH", "clinic": "Test"},
                           files={"image": ("b.jpg", _jpeg((235, 60, 90)), "image/jpeg")})
        assert low.status_code == high.status_code == 201

        # TestClient runs background tasks before returning, so results are ready.
        detail = client.get(f"/api/cases/{high.json()['id']}").json()
        assert detail["status"] == "ready"
        assert detail["result"]["regions"]
        assert client.get(detail["heatmap_url"]).status_code == 200

        queue = client.get("/api/cases?status=active").json()
        assert [c["patient_ref"] for c in queue[:2]] == ["P-HIGH", "P-LOW"]
        assert queue[0]["urgency"] > queue[1]["urgency"]

        r = client.patch(f"/api/cases/{high.json()['id']}", json={"status": "reviewed", "diagnosis": "Adenocarcinoma"})
        assert r.json()["reviewed_at"]
        active = client.get("/api/cases?status=active").json()
        assert "P-HIGH" not in [c["patient_ref"] for c in active]


def test_rejects_non_images():
    from app.main import app

    with TestClient(app) as client:
        r = client.post("/api/cases", data={"patient_ref": "X"},
                        files={"image": ("a.jpg", io.BytesIO(b"not an image"), "image/jpeg")})
        assert r.status_code == 422
        r = client.post("/api/cases", data={"patient_ref": "X"},
                        files={"image": ("a.exe", io.BytesIO(b"x"), "application/octet-stream")})
        assert r.status_code == 415
