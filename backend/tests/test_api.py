import io

import numpy as np
import torch
from fastapi.testclient import TestClient
from PIL import Image

from app.inference import model as model_mgr
from app.inference.quality import QualityReport
from app.inference.registry import get_profile
from tests.test_engine import FakeModel


def _jpeg(color):
    buf = io.BytesIO()
    arr = np.full((500, 600, 3), (150, 90, 160), np.uint8)
    arr[50:450, 50:550] = color
    Image.fromarray(arr).save(buf, "JPEG")
    buf.seek(0)
    return buf


def test_upload_analyze_queue_review(monkeypatch):
    fake = model_mgr.Loaded(get_profile("resnet18-kather100k"), FakeModel(), torch.device("cpu"))
    monkeypatch.setattr("app.worker.load_model", lambda: fake)
    monkeypatch.setattr(model_mgr, "warm", lambda: None)
    # Flat synthetic colour blocks would fail the focus check; this test is about the queue.
    monkeypatch.setattr("app.worker.assess", lambda img: QualityReport("pass"))
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
        assert detail["result"]["model"] == "resnet18-kather100k"
        assert detail["result"]["model"] == "resnet18-kather100k"
        assert client.get(detail["heatmap_url"]).status_code == 200

        queue = client.get("/api/cases?status=active").json()
        assert [c["patient_ref"] for c in queue[:2]] == ["P-HIGH", "P-LOW"]
        assert queue[0]["urgency"] > queue[1]["urgency"]

        r = client.patch(f"/api/cases/{high.json()['id']}", json={"status": "reviewed", "diagnosis": "Adenocarcinoma"})
        assert r.json()["reviewed_at"]
        active = client.get("/api/cases?status=active").json()
        assert "P-HIGH" not in [c["patient_ref"] for c in active]


def test_rejects_non_images(monkeypatch):
    monkeypatch.setattr(model_mgr, "warm", lambda: None)
    from app.main import app

    with TestClient(app) as client:
        r = client.post("/api/cases", data={"patient_ref": "X"},
                        files={"image": ("a.jpg", io.BytesIO(b"not an image"), "image/jpeg")})
        assert r.status_code == 422
        r = client.post("/api/cases", data={"patient_ref": "X"},
                        files={"image": ("a.exe", io.BytesIO(b"x"), "application/octet-stream")})
        assert r.status_code == 415


def test_multi_photo_upload_is_stitched_and_counted(monkeypatch):
    from app import config
    from app.inference import cells
    from tests.test_stitch_cells import _eyepiece, _texture

    fake = model_mgr.Loaded(get_profile("resnet18-kather100k"), FakeModel(), torch.device("cpu"))
    monkeypatch.setattr("app.worker.load_model", lambda: fake)
    monkeypatch.setattr(model_mgr, "warm", lambda: None)
    monkeypatch.setattr(config, "CELL_COUNTING", True)
    monkeypatch.setattr(cells, "count_cells", lambda img, device, tissue_fraction, **kw: cells.CellResult(
        total=2, counts={"neoplastic": 1, "inflammatory": 1}, fractions={}, per_mm2=1.0, tissue_mm2=2.0,
        elapsed_ms=1, scale=2.0, points=[(10, 20, 1), (30, 40, 2)]))
    from app.main import app

    slide = _texture(900, 1300)
    files = []
    for i, (y, x) in enumerate((y, x) for y in (0, 300) for x in (0, 350, 700)):
        buf = io.BytesIO()
        _eyepiece(slide[y : y + 600, x : x + 600]).save(buf, "JPEG", quality=92)
        files.append(("images", (f"f{i}.jpg", buf.getvalue(), "image/jpeg")))

    with TestClient(app) as client:
        r = client.post("/api/cases", data={"patient_ref": "P-MOSAIC"}, files=files)
        assert r.status_code == 201 and len(r.json()["field_urls"]) == 6
        c = client.get(f"/api/cases/{r.json()['id']}").json()
        assert c["status"] == "ready", c["error"]
        assert c["result"]["fields"]["stitched"] == 6
        assert abs(c["result"]["width"] - 1300) < 60
        assert c["result"]["cells"]["status"] == "done" and c["result"]["cells"]["total"] == 2
        assert client.get(c["nuclei_url"]).json()["points"] == [[10, 20, 1], [30, 40, 2]]


def test_unrelated_photos_fail_with_guidance(monkeypatch):
    from tests.test_stitch_cells import _eyepiece, _texture

    monkeypatch.setattr(model_mgr, "warm", lambda: None)
    from app.main import app

    files = []
    for seed in (1, 2):
        buf = io.BytesIO()
        _eyepiece(_texture(600, 600, seed=seed)).save(buf, "JPEG")
        files.append(("images", (f"{seed}.jpg", buf.getvalue(), "image/jpeg")))
    with TestClient(app) as client:
        r = client.post("/api/cases", data={"patient_ref": "P-BAD"}, files=files)
        c = client.get(f"/api/cases/{r.json()['id']}").json()
        assert c["status"] == "failed" and "Overlap" in c["error"]


def _photo(blur=0.0, dark=False):
    from PIL import ImageFilter

    src = np.full((900, 1200, 3), (235, 225, 235), np.uint8)
    rng = np.random.default_rng(0)
    for y, x in rng.integers(0, [900, 1200], size=(2500, 2)):  # purple 'nuclei' on pink tissue
        src[max(0, y - 5) : y + 5, max(0, x - 5) : x + 5] = (110, 50, 150)
    src[:, :] = np.where(src == (235, 225, 235), np.array((215, 140, 190), np.uint8), src)
    img = Image.fromarray(src).filter(ImageFilter.GaussianBlur(blur)) if blur else Image.fromarray(src)
    if dark:
        img = img.point(lambda v: v // 5)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=92)
    buf.seek(0)
    return buf


def test_quality_gate_asks_for_retake_and_can_be_overridden(monkeypatch):
    fake = model_mgr.Loaded(get_profile("resnet18-kather100k"), FakeModel(), torch.device("cpu"))
    monkeypatch.setattr("app.worker.load_model", lambda: fake)
    monkeypatch.setattr(model_mgr, "warm", lambda: None)
    from app.main import app

    with TestClient(app) as client:
        r = client.post("/api/cases", data={"patient_ref": "P-BLUR"},
                        files={"image": ("b.jpg", _photo(blur=6), "image/jpeg")})
        c = client.get(f"/api/cases/{r.json()['id']}").json()
        assert c["status"] == "retake" and "focus" in c["error"]
        assert c["quality"]["status"] == "reject" and c["result"] is None
        assert "P-BLUR" in [x["patient_ref"] for x in client.get("/api/cases?status=active").json()]

        client.post(f"/api/cases/{c['id']}/reanalyze?force=true")
        c = client.get(f"/api/cases/{c['id']}").json()
        assert c["status"] == "ready" and c["quality"]["forced"] is True

        r = client.post("/api/cases", data={"patient_ref": "P-SHARP"},
                        files={"image": ("s.jpg", _photo(), "image/jpeg")})
        c = client.get(f"/api/cases/{r.json()['id']}").json()
        assert c["status"] == "ready" and c["quality"]["status"] == "pass", c["quality"]


def test_dark_photo_rejected():
    from app.inference.quality import assess

    report = assess(Image.open(_photo(dark=True)))
    assert report.status == "reject"
    assert any(ch.name == "exposure_dark" and ch.status == "reject" for ch in report.checks)


def test_restart_resumes_interrupted_cases(monkeypatch):
    from sqlmodel import Session

    from app.db import engine
    from app.models import Case
    from app.worker import case_dir, resume_interrupted

    fake = model_mgr.Loaded(get_profile("resnet18-kather100k"), FakeModel(), torch.device("cpu"))
    monkeypatch.setattr("app.worker.load_model", lambda: fake)
    monkeypatch.setattr("app.worker.assess", lambda img: QualityReport("pass"))
    with Session(engine) as session:
        c = Case(patient_ref="P-CRASH", filename="original.jpg", status="analyzing")
        session.add(c)
        session.commit()
        session.refresh(c)
        (case_dir(c.id) / "original.jpg").write_bytes(_jpeg((235, 60, 90)).getvalue())
        case_id = c.id
    resume_interrupted()
    with Session(engine) as session:
        assert session.get(Case, case_id).status == "ready"
