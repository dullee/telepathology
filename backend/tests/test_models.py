import json
from types import SimpleNamespace

import pytest
import torch
from fastapi.testclient import TestClient

from app import config
from app.inference import foundation, registry
from app.inference import model as model_mgr


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setattr(model_mgr, "warm", lambda: None)
    monkeypatch.setattr(model_mgr, "_SETTINGS", tmp_path / "active_model.json")
    monkeypatch.setattr(model_mgr, "_active_id", registry.DEFAULT_ID)
    monkeypatch.setattr(registry, "HEADS_DIR", tmp_path / "heads")
    monkeypatch.setattr(registry.ModelProfile, "weights_cached", lambda self: False)
    from app.main import app

    with TestClient(app) as c:
        yield c


def test_list_and_switch_models(client, tmp_path):
    status = client.get("/api/models").json()
    assert status["active"] == registry.DEFAULT_ID
    ids = {m["id"]: m for m in status["models"]}
    assert ids["midnight-kather100k"]["family"] == "foundation"
    assert {m["organ"] for m in status["models"]} == {"Colorectal", "Stomach", "Liver", "Lung"}
    assert ids["midnight-lung"]["tumor_classes"] == ["ACA", "SCC"]
    assert not ids["midnight-kather100k"]["available"], "no head trained in the temp heads dir"

    r = client.put("/api/models/active", json={"id": "mobilenet_v3_large-kather100k"})
    assert r.status_code == 200 and r.json()["active"] == "mobilenet_v3_large-kather100k"
    assert json.loads((tmp_path / "active_model.json").read_text())["model"] == "mobilenet_v3_large-kather100k"
    assert client.get("/api/health").json()["model"] == "mobilenet_v3_large-kather100k"


def test_switch_rejects_unknown_and_untrained(client):
    assert client.put("/api/models/active", json={"id": "nope"}).status_code == 404
    r = client.put("/api/models/active", json={"id": "midnight-kather100k"})
    assert r.status_code == 409 and "train_head.py" in r.json()["detail"]
    assert client.get("/api/models").json()["active"] == registry.DEFAULT_ID


def test_uncurated_tiatoolbox_backbone_is_accepted():
    p = registry.get_profile("densenet161-kather100k")
    assert p.family == "cnn" and p.tiatoolbox_name == "densenet161-kather100k"


class TinyBackbone(torch.nn.Module):
    """Stands in for a ViT: returns 4 'tokens' of width 8 derived from the pixels."""

    def __init__(self):
        super().__init__()
        self.proj = torch.nn.Linear(3, 8)

    def forward(self, pixel_values):
        tokens = self.proj(pixel_values.mean(dim=(2, 3))).unsqueeze(1).repeat(1, 4, 1)
        return SimpleNamespace(last_hidden_state=tokens)


def test_foundation_classifier_outputs_class_probabilities(tmp_path, monkeypatch):
    monkeypatch.setattr(registry, "HEADS_DIR", tmp_path)
    profile = registry.get_profile("midnight-liver")  # 7 classes, 150px centre crop
    n = len(profile.spec.classes)
    torch.save({"weight": torch.randn(n, 16), "bias": torch.zeros(n), "classes": list(profile.spec.classes)},
               profile.head_path)
    monkeypatch.setattr(foundation, "load_backbone", lambda p, d: TinyBackbone())

    clf = foundation.build_classifier(profile, torch.device("cpu"))
    probs = clf(torch.rand(5, 3, config.TILE, config.TILE))
    assert probs.shape == (5, n)
    assert torch.allclose(probs.sum(1), torch.ones(5))
    assert profile.availability() == (True, "")
    assert clf.embedder.crop_px == 150


def test_fit_input_crops_then_resizes():
    x = torch.zeros(1, 3, config.TILE, config.TILE)
    x[..., 37:187, 37:187] = 1  # the centre 150px
    out = foundation.fit_input(x, crop_px=150)
    assert out.shape[-2:] == (config.TILE, config.TILE) and out.min() == 1


def test_head_with_wrong_classes_is_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(registry, "HEADS_DIR", tmp_path)
    profile = registry.get_profile("midnight-kather100k")
    torch.save({"weight": torch.zeros(2, 16), "bias": torch.zeros(2), "classes": ["A", "B"]}, profile.head_path)
    with pytest.raises(ValueError):
        foundation.load_head(profile)


def test_gpu_scheduler_puts_triage_before_background_work():
    """Background cell counting must yield to a case waiting for its urgency score."""
    import threading
    import time

    gpu = model_mgr.GpuScheduler()
    order: list[str] = []

    def background_job():
        for i in range(5):  # cell counting: one chunk per slot
            with gpu.background():
                order.append(f"chunk{i}")
                time.sleep(0.05)

    t = threading.Thread(target=background_job)
    t.start()
    time.sleep(0.07)  # mid-way through chunk 1
    with gpu.urgent():
        order.append("triage")
    t.join()
    assert order.index("triage") <= 2, order  # got in after at most the chunk in progress
    assert order.count("triage") == 1 and len(order) == 6
