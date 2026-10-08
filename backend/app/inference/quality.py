"""Photo quality gate, run before any model sees the image.

Each check returns pass / warn / reject. A reject stops analysis and asks the clinic to retake the
photo (a reviewer can still force analysis). A warn lets analysis run but is shown with the result.

Focus thresholds were calibrated on LungHist700 microscope-camera photos with added Gaussian blur.
`focus` is the median, over tissue tiles, of var(Laplacian) / var(gray): it is contrast- and
stain-independent. Typical values:

  sharp camera photo ~3.2 · 0.8 px blur ~1.3 · 1.6 px blur ~0.3 · 2.5 px blur ~0.1 · scanner tiles ~6

At 0.8 px blur, HoVer-Net nucleus typing already collapses (neoplastic 50% -> 13%), hence WARN at 1.5.
Tissue classification survives moderate blur, so REJECT only below 0.4 (about 1.5-2 px of blur).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

import cv2
import numpy as np
from PIL import Image

FOCUS_WARN, FOCUS_REJECT = 1.5, 0.4
TISSUE_WARN, TISSUE_REJECT = 0.15, 0.03
DARK_WARN, DARK_REJECT = 90, 55  # median brightness of the lit field (0-255)
CLIP_WARN, CLIP_REJECT = 0.35, 0.7  # share of lit-field pixels clipped to white
STAIN_WARN, STAIN_REJECT = 0.5, 0.2  # share of tissue pixels with H&E colouring
SIDE_WARN, SIDE_REJECT = 1000, 224  # longest side, px
TILE = 224
RANK = {"pass": 0, "warn": 1, "reject": 2}


@dataclass
class Check:
    name: str
    label: str
    status: str  # "pass" | "warn" | "reject"
    value: float
    message: str = ""


@dataclass
class QualityReport:
    status: str
    checks: list[Check] = field(default_factory=list)
    # Stitched cases: photos that were left out before stitching, and why.
    dropped: list[dict] = field(default_factory=list)

    @property
    def problems(self) -> list[Check]:
        return [c for c in self.checks if c.status != "pass"]

    def summary(self, only: str | None = None) -> str:
        """Messages of every failed check, or only those with status `only` (e.g. "reject")."""
        return " ".join(c.message for c in self.problems if c.message and (only is None or c.status == only)) or "Photo quality OK."

    def to_dict(self) -> dict:
        return asdict(self)


def _grade(value: float, warn: float, reject: float, *, higher_is_better: bool = True) -> str:
    if higher_is_better:
        return "reject" if value < reject else "warn" if value < warn else "pass"
    return "reject" if value > reject else "warn" if value > warn else "pass"


def assess(img: Image.Image) -> QualityReport:
    """Grade an RGB photo at the analysis scale (see engine.prepare_image)."""
    rgb = np.asarray(img.convert("RGB"))
    f = rgb.astype(np.float32)
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY).astype(np.float32)
    mean, sat = f.mean(axis=2), f.max(axis=2) - f.min(axis=2)
    lit = mean > 40  # inside the eyepiece field
    tissue = lit & ~((mean > 215) & (sat < 18))  # same rule as the engine's tissue mask
    checks: list[Check] = []

    side = max(img.size)
    st = _grade(side, SIDE_WARN, SIDE_REJECT)
    checks.append(Check("resolution", "Resolution", st, side, {
        "reject": "The image is too small to analyse; send the original camera photo.",
        "warn": "Low-resolution image: results are based on very few tiles.",
    }.get(st, "")))

    brightness = float(np.median(gray[lit])) if lit.any() else 0.0
    st = _grade(brightness, DARK_WARN, DARK_REJECT)
    checks.append(Check("exposure_dark", "Brightness", st, round(brightness, 1), {
        "reject": "The photo is too dark: turn up the microscope lamp or open the condenser.",
        "warn": "The photo is dim; colours may be distorted.",
    }.get(st, "")))

    clipped = float((f[lit].min(axis=1) >= 252).mean()) if lit.any() else 0.0
    st = _grade(clipped, CLIP_WARN, CLIP_REJECT, higher_is_better=False)
    checks.append(Check("exposure_bright", "Overexposure", st, round(clipped, 3), {
        "reject": "The photo is washed out: lower the lamp or tap the tissue to set exposure.",
        "warn": "Parts of the photo are overexposed.",
    }.get(st, "")))

    coverage = float(tissue.mean())
    st = _grade(coverage, TISSUE_WARN, TISSUE_REJECT)
    checks.append(Check("tissue", "Tissue in view", st, round(coverage, 3), {
        "reject": "Almost no tissue is visible: centre the section in the field.",
        "warn": "Little tissue is in view; the score covers only a small area.",
    }.get(st, "")))

    if tissue.sum() > 500:
        # H&E: haematoxylin purple and eosin pink both have green clearly the weakest channel
        # (grey, unstained or green-tinted pixels don't).
        t = f[tissue]
        r, g, b = t[:, 0], t[:, 1], t[:, 2]
        stain = float(((g <= r) & (g <= b) & (np.maximum(r, b) - g > 12)).mean())
        st = _grade(stain, STAIN_WARN, STAIN_REJECT)
        checks.append(Check("stain", "H&E staining", st, round(stain, 3), {
            "reject": "This doesn't look like an H&E-stained slide.",
            "warn": "Unusual colours for H&E: check the white balance or the stain.",
        }.get(st, "")))

    # Focus: median over tiles that are mostly tissue (falls back to the whole tissue area).
    lap = cv2.Laplacian(gray, cv2.CV_32F, ksize=3)
    scores = [
        lap[y : y + TILE, x : x + TILE].var() / (gray[y : y + TILE, x : x + TILE].var() + 1e-3)
        for y in range(0, gray.shape[0] - TILE + 1, TILE)
        for x in range(0, gray.shape[1] - TILE + 1, TILE)
        if tissue[y : y + TILE, x : x + TILE].mean() > 0.5
    ]
    if not scores and tissue.sum() > 500:
        scores = [float(lap[tissue].var() / (gray[tissue].var() + 1e-3))]
    if scores:
        focus = float(np.median(scores))
        st = _grade(focus, FOCUS_WARN, FOCUS_REJECT)
        checks.append(Check("focus", "Focus", st, round(focus, 2), {
            "reject": "The photo is out of focus: refocus with the fine-focus knob and hold the phone still.",
            "warn": "Slightly soft focus: tumor detection is usable, but cell types are unreliable.",
        }.get(st, "")))

    worst = max((c.status for c in checks), key=RANK.__getitem__, default="pass")
    return QualityReport(status=worst, checks=checks)
