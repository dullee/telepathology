import numpy as np
import pytest
import torch
from PIL import Image

from app import config
from app.inference import engine


class FakeModel(torch.nn.Module):
    """Calls a tile 'tumor' when its mean red channel is high, else 'stroma'."""

    def forward(self, x):
        red = x[:, 0].mean(dim=(1, 2))
        p = torch.zeros(x.shape[0], len(config.CLASSES))
        tum = (red > 0.7).float()
        p[:, config.CLASSES.index("TUM")] = tum
        p[:, config.CLASSES.index("STR")] = 1 - tum
        return p


@pytest.fixture
def synthetic(tmp_path):
    arr = np.full((700, 900, 3), (150, 90, 160), np.uint8)  # pinkish-purple tissue
    arr[100:400, 450:850] = (230, 60, 90)  # "tumor" block on the right
    path = tmp_path / "slide.jpg"
    Image.fromarray(arr).save(path)
    return path


def test_analyze_outputs_match_image(synthetic, tmp_path):
    res = engine.analyze(synthetic, tmp_path / "d.jpg", tmp_path / "h.png", FakeModel(), torch.device("cpu"))
    heat = Image.open(tmp_path / "h.png")
    assert heat.size == (res.width, res.height) == (900, 700)
    assert heat.mode == "RGBA"
    s = config.STRIDE
    assert res.grid_shape == (-(-700 // s), -(-900 // s))
    assert res.tiles > 0 and 0 < res.tumor_fraction < 1
    assert res.regions, "the red block should be found as a region"
    r = res.regions[0]
    # Region sits on the right half where the block was drawn.
    assert r.x0 >= 300 and r.x1 <= 900 and r.y1 <= 560
    assert res.urgency > 0


def test_blank_image_has_no_tissue(tmp_path):
    path = tmp_path / "blank.png"
    Image.fromarray(np.full((300, 300, 3), 250, np.uint8)).save(path)
    res = engine.analyze(path, tmp_path / "d.jpg", tmp_path / "h.png", FakeModel(), torch.device("cpu"))
    assert res.tissue_fraction == 0 and res.urgency == 0 and res.tier == "routine"


def test_small_image_is_padded(tmp_path):
    path = tmp_path / "tiny.png"
    Image.fromarray(np.full((100, 150, 3), (150, 90, 160), np.uint8)).save(path)
    res = engine.analyze(path, tmp_path / "d.jpg", tmp_path / "h.png", FakeModel(), torch.device("cpu"))
    assert res.tiles == 1 and (res.width, res.height) == (150, 100)


def test_hotspot_landmarks_and_tissue_map(synthetic, tmp_path):
    res = engine.analyze(
        synthetic, tmp_path / "d.jpg", tmp_path / "h.png", FakeModel(), torch.device("cpu"),
        tissue_map_path=tmp_path / "t.png",
    )
    r = res.regions[0]
    assert r.x0 <= r.hotspot_x < r.x1 and r.y0 <= r.hotspot_y < r.y1
    # The hotspot lands inside the red block that was drawn as "tumor".
    assert 450 <= r.hotspot_x < 850 and 100 <= r.hotspot_y < 400

    stroma = [lm for lm in res.landmarks if lm.cls == "STR"]
    assert stroma and not (450 <= stroma[0].x < 850 and 100 <= stroma[0].y < 400)

    tmap = Image.open(tmp_path / "t.png")
    assert tmap.size == (res.width, res.height) and tmap.mode == "RGBA"
    assert tmap.getpixel((r.hotspot_x, r.hotspot_y))[:3] == config.TISSUE_COLORS["TUM"]


class FakeLungModel(torch.nn.Module):
    """Splits red tiles' tumor mass across both carcinoma classes, so neither alone passes 0.5."""

    def forward(self, x):
        red = (x[:, 0].mean(dim=(1, 2)) > 0.7).float()
        p = torch.zeros(x.shape[0], 3)  # NOR, ACA, SCC
        p[:, 0] = 1 - red
        p[:, 1] = 0.45 * red
        p[:, 2] = 0.55 * red
        return p


def test_spec_with_two_tumor_classes(synthetic, tmp_path):
    from app.inference.registry import LUNG

    res = engine.analyze(
        synthetic, tmp_path / "d.jpg", tmp_path / "h.png", FakeLungModel(), torch.device("cpu"), LUNG,
        tissue_map_path=tmp_path / "t.png",
    )
    assert set(res.composition) == {"NOR", "ACA", "SCC"}
    assert res.regions and res.max_tumor_prob > 0.9, "ACA + SCC should add up to one tumor signal"
    assert res.necrosis_fraction == 0
    # Landmarks and the tissue map follow the lung classes, not the colorectal ones.
    assert [lm.cls for lm in res.landmarks] == ["NOR"]
    r = res.regions[0]
    tmap = Image.open(tmp_path / "t.png")
    assert tmap.getpixel((r.hotspot_x, r.hotspot_y))[:3] == config.TISSUE_COLORS["SCC"]
