import numpy as np
import pytest
import torch
from PIL import Image
from scipy import ndimage

from app.inference import cells, stitch


def _texture(h, w, seed=0):
    """Tissue-like random texture: smoothed noise in pink/purple tones with dark 'nuclei'."""
    rng = np.random.default_rng(seed)
    base = ndimage.gaussian_filter(rng.random((h, w)), 6)
    base = (base - base.min()) / (base.max() - base.min())
    img = np.stack([200 - 60 * base, 120 - 50 * base, 190 - 30 * base], axis=2)
    for y, x in rng.integers(0, [h, w], size=(h * w // 900, 2)):
        img[max(0, y - 4) : y + 4, max(0, x - 4) : x + 4] = (90, 40, 140)
    return img.clip(0, 255).astype(np.uint8)


def _eyepiece(arr):
    h, w = arr.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w]
    d = np.hypot((xx - w / 2) / (w / 2), (yy - h / 2) / (h / 2))
    return Image.fromarray((arr * np.clip((1.0 - d) / 0.08, 0, 1)[..., None]).astype(np.uint8))


def test_stitch_recovers_layout():
    slide = _texture(900, 1300)
    fields = [_eyepiece(slide[y : y + 600, x : x + 600]) for y in (0, 300) for x in (0, 350, 700)]
    m = stitch.stitch(fields[::-1])
    assert m.used == m.total == 6
    # Mosaic spans the photographed area (1300 x 900) give or take the trimmed rims.
    assert abs(m.image.width - 1300) < 60 and abs(m.image.height - 900) < 60


def test_stitch_rejects_unrelated_photos():
    a, b = _eyepiece(_texture(600, 600, seed=1)), _eyepiece(_texture(600, 600, seed=2))
    with pytest.raises(stitch.StitchError):
        stitch.stitch([a, b])


def _locate(mosaic: Image.Image, slide: np.ndarray, y: int, x: int, size: int = 200):
    """Where the slide patch at (y, x) appears in the mosaic: (offset y, offset x, match score)."""
    import cv2

    tpl = cv2.cvtColor(slide[y : y + size, x : x + size], cv2.COLOR_RGB2GRAY)
    img = cv2.cvtColor(np.asarray(mosaic), cv2.COLOR_RGB2GRAY)
    res = cv2.matchTemplate(img, tpl, cv2.TM_CCOEFF_NORMED)
    _, score, _, (fx, fy) = cv2.minMaxLoc(res)
    return fy - y, fx - x, score


def _grid(slide, size, ys, xs):
    return [_eyepiece(slide[y : y + size, x : x + size]) for y in ys for x in xs]


def test_stitch_is_geometrically_consistent():
    """Patches on opposite sides of several seams land at the same offset: no tearing or drift."""
    slide = _texture(900, 1300, seed=3)
    m = stitch.stitch(_grid(slide, 600, (0, 300), (0, 350, 700)))
    offsets = [_locate(m.image, slide, y, x) for y, x in ((200, 200), (200, 900), (600, 250), (600, 950), (400, 550))]
    assert all(score > 0.9 for *_, score in offsets), offsets
    oy, ox = offsets[0][:2]
    assert all(abs(dy - oy) <= 2 and abs(dx - ox) <= 2 for dy, dx, _ in offsets), offsets


def test_stitch_long_sweep_without_drift():
    """A 1 x 6 sweep along the slide: errors could accumulate along the chain of matches."""
    slide = _texture(600, 2600, seed=4)
    m = stitch.stitch(_grid(slide, 600, (0,), range(0, 2001, 400)))
    assert m.used == 6
    assert abs(m.image.width - 2600) < 60
    left, right = _locate(m.image, slide, 200, 150), _locate(m.image, slide, 200, 2250)
    assert left[2] > 0.9 and right[2] > 0.9
    assert abs(left[0] - right[0]) <= 3 and abs(left[1] - right[1]) <= 3, (left, right)


def test_stitch_handles_rotated_photos():
    """The phone isn't always held square: each photo is rotated a few degrees."""
    slide = _texture(1000, 1400, seed=5)
    fields = []
    for i, (y, x) in enumerate((y, x) for y in (0, 350) for x in (0, 400, 750)):
        crop = Image.fromarray(slide[y : y + 650, x : x + 650]).rotate((-4, 3, -2, 5, -3, 2)[i], Image.BICUBIC)
        fields.append(_eyepiece(np.asarray(crop)))
    m = stitch.stitch(fields)
    assert m.used == 6
    # Rotation can't make the mosaic much bigger than the photographed area plus a margin.
    assert m.image.width < 1550 and m.image.height < 1150


def test_stitch_evens_out_exposure_differences():
    """Photos at different brightness blend without a visible step at the seam."""
    slide = _texture(600, 1000, seed=6)
    a = _eyepiece((slide[:, :600] * 0.8).astype(np.uint8))
    b = _eyepiece(np.clip(slide[:, 400:] * 1.15, 0, 255).astype(np.uint8))
    m = stitch.stitch([a, b])
    oy, ox, score = _locate(m.image, slide, 200, 100)  # anchor away from the seam's brightness ramp
    assert score > 0.9
    # Brightness gain of the mosaic relative to the true slide, column by column, mid rows.
    mos = np.asarray(m.image, np.float32)[250 + oy : 350 + oy, 100 + ox : 900 + ox].mean(axis=(0, 2))
    ref = slide[250:350, 100:900].astype(np.float32).mean(axis=(0, 2))
    gain = ndimage.uniform_filter1d(mos / ref, 9)
    assert abs(gain[:50].mean() - 0.8) < 0.05 and abs(gain[-50:].mean() - 1.15) < 0.05
    # Feathered blend: the 0.8 -> 1.15 change is spread over the overlap, not a step at one seam.
    assert np.abs(np.diff(gain)).max() < 0.02


def test_stitch_leaves_out_unrelated_photo():
    slide = _texture(900, 1000, seed=7)
    fields = _grid(slide, 600, (0, 300), (0, 400))
    stray = _eyepiece(_texture(600, 600, seed=99))
    m = stitch.stitch(fields[:2] + [stray] + fields[2:])
    assert (m.used, m.total) == (4, 5)


def test_stitch_tolerates_duplicate_photo():
    slide = _texture(900, 1000, seed=8)
    fields = _grid(slide, 600, (0, 300), (0, 400))
    m = stitch.stitch(fields + [fields[1]])
    assert m.used == 5 and abs(m.image.width - 1000) < 60


def test_stitch_downscales_huge_mosaic(monkeypatch):
    from app import config

    monkeypatch.setattr(config, "MOSAIC_MAX_SIDE", 500)
    slide = _texture(900, 1300, seed=9)
    m = stitch.stitch(_grid(slide, 600, (0, 300), (0, 350, 700)))
    assert max(m.image.size) <= 501 and 0.3 < m.downscale < 0.45


def test_stitch_needs_two_photos():
    with pytest.raises(stitch.StitchError):
        stitch.stitch([_eyepiece(_texture(600, 600))])


def test_field_mask_excludes_eyepiece_ring():
    arr = np.asarray(_eyepiece(_texture(600, 600, seed=10)))
    mask = stitch.field_mask(arr)
    assert mask[300, 300] and not mask[5, 5] and not mask[300, 2]
    assert 0.6 < mask.mean() < 0.78  # inscribed disc (~0.785) minus the trimmed rim


def test_field_mask_keeps_dark_tissue_at_the_edge():
    """Regression: dense, dark nuclei touching the field stop were masked out as 'ring',
    leaving black holes in the mosaic."""
    tex = _texture(600, 600, seed=11)
    tex[200:400, 0:220] = (45, 20, 60)  # very dark tissue reaching the left edge of the field
    mask = stitch.field_mask(np.asarray(_eyepiece(tex)))
    assert mask[300, 120] and mask[300, 200]


def test_cell_count_chunking(monkeypatch):
    """Fake HoVer-Net that 'segments' dark dots: every dot must be found once, in place,
    including dots on chunk borders (CORE / scale = 512 display px)."""

    def fake_predict(model, region, device):
        k = (region.shape[0] - 2 * cells.CTX) // cells.OUT
        out = region[cells.CTX : cells.CTX + k * cells.OUT, cells.CTX : cells.CTX + k * cells.OUT]
        blobs = out.mean(axis=2) < 80
        # HoVer-Net's hv maps: each pixel's x/y offset from its nucleus centre, scaled to [-1, 1].
        hv = np.zeros((*blobs.shape, 2), np.float32)
        labels, n = ndimage.label(blobs)
        for i, (sy, sx) in enumerate(ndimage.find_objects(labels), start=1):
            yy, xx = np.nonzero(labels == i)
            hv[yy, xx, 0] = (xx - xx.mean()) / max(1, np.abs(xx - xx.mean()).max())
            hv[yy, xx, 1] = (yy - yy.mean()) / max(1, np.abs(yy - yy.mean()).max())
        np_map = blobs.astype(np.float32)[..., None]
        return np_map, hv, np.ones_like(np_map)

    monkeypatch.setattr(cells, "_predict", fake_predict)
    monkeypatch.setattr(cells, "load_hovernet", lambda device_type: None)
    img = np.full((700, 1100, 3), (200, 150, 190), np.uint8)
    dots = [(100, 100), (507, 300), (517, 300), (900, 650), (60, 512)]  # some straddle x/y = 512
    for x, y in dots:
        yy, xx = np.ogrid[:700, :1100]
        img[(yy - y) ** 2 + (xx - x) ** 2 <= 9] = (20, 20, 20)
    res = cells.count_cells(Image.fromarray(img), torch.device("cpu"), tissue_fraction=1.0, scale=2.0)
    assert res.total == len(dots)
    found = sorted((x, y) for x, y, _ in res.points)
    for (x, y), (fx, fy) in zip(sorted(dots), found):
        assert abs(x - fx) <= 1 and abs(y - fy) <= 1
    assert res.counts["neoplastic"] == len(dots)
