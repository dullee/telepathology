"""Typed nucleus counting with HoVer-Net (PanNuke weights from TIAToolbox).

HoVer-Net was trained at 0.25 µm/px (40x). Phone photos through a 20x objective are about
0.5 µm/px, so the image is upscaled by CELL_SCALE first. Work is done in chunks so a large
mosaic never has to exist at 40x in memory:

  chunk core (CORE px at model scale) + MARGIN on every side = 7 x 164 px HoVer-Net outputs,
  each predicted from a 256 px input. Instances are segmented on the whole chunk and kept only
  if their centroid lies in the core, so nuclei on chunk borders are counted exactly once.

Note: the PanNuke dataset is CC BY-NC-SA 4.0, so these weights are for non-commercial use.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from contextlib import AbstractContextManager as ContextManager
from contextlib import nullcontext
from dataclasses import asdict, dataclass, field
from functools import lru_cache

import numpy as np
import torch
from PIL import Image

from app import config

log = logging.getLogger(__name__)

MODEL_NAME = "hovernet_fast-pannuke"
TYPES = {1: "neoplastic", 2: "inflammatory", 3: "connective", 4: "dead", 5: "epithelial"}
IN, OUT = 256, 164  # HoVer-Net fast: 256 px input -> 164 px centre output
CTX = (IN - OUT) // 2
MARGIN = 62
CORE = 7 * OUT - 2 * MARGIN  # 1024


def batch_size(device: torch.device) -> int:
    # HoVer-Net keeps large full-resolution activations: on 8 GB Macs batches > 1 push the
    # system into swap and run slower than batch 1. A CUDA card handles 16 comfortably.
    return int(config.CELL_BATCH or (16 if device.type == "cuda" else 1))


@dataclass
class CellResult:
    total: int
    counts: dict[str, int]
    fractions: dict[str, float]
    per_mm2: float  # nuclei per mm² of tissue
    tissue_mm2: float
    elapsed_ms: int
    scale: float
    # (x, y, type) in display-image pixels; written to nuclei.json, not the DB.
    points: list[tuple[int, int, int]] = field(default_factory=list, repr=False)

    def summary(self) -> dict:
        d = asdict(self)
        d.pop("points")
        return d


@lru_cache(maxsize=1)
def load_hovernet(device_type: str) -> torch.nn.Module:
    from tiatoolbox.models.architecture import get_pretrained_model

    model, _ = get_pretrained_model(MODEL_NAME)
    return model.to(device_type).eval()


def _has_tissue(rgb: np.ndarray) -> bool:
    """Same rule as the engine's pixel tissue mask: not dark vignette, not blank glass."""
    a = np.asarray(rgb, np.float32)
    mean = a.mean(axis=2)
    sat = a.max(axis=2) - a.min(axis=2)
    tissue = (mean > 40) & ~((mean > 215) & (sat < 18))
    return tissue.mean() > 0.02


@torch.inference_mode()
def _predict(model, region: np.ndarray, device: torch.device) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """region: (R + 2*CTX)^2 x 3 uint8 -> np, hv, tp maps of R x R, R = 7 * OUT."""
    from tiatoolbox.models.architecture.hovernet import HoVerNet

    k = (region.shape[0] - 2 * CTX) // OUT
    # Skip patches whose output area is blank glass or eyepiece ring: no nuclei to find.
    origins = [
        (y * OUT, x * OUT)
        for y in range(k)
        for x in range(k)
        if _has_tissue(region[y * OUT + CTX : y * OUT + CTX + OUT, x * OUT + CTX : x * OUT + CTX + OUT])
    ]
    maps = [np.zeros((k * OUT, k * OUT, c), np.float32) for c in (1, 2, 1)]
    step = batch_size(device)
    for i in range(0, len(origins), step):
        chunk = origins[i : i + step]
        batch = torch.from_numpy(np.stack([region[y : y + IN, x : x + IN] for y, x in chunk]))
        outs = HoVerNet.infer_batch(model, batch, device=str(device))
        for n, (y, x) in enumerate(chunk):
            for m, o in zip(maps, outs):
                m[y : y + OUT, x : x + OUT] = o[n]
    return maps[0], maps[1], maps[2]


def count_cells(
    img: Image.Image,
    device: torch.device,
    tissue_fraction: float,
    scale: float | None = None,
    gpu: Callable[[], ContextManager] = nullcontext,
) -> CellResult:
    """Count and type nuclei in a display-scale RGB image (the one the heatmap is drawn on).

    `gpu` is entered around each chunk's GPU work only (not CPU post-processing), so a scheduler
    can let urgent jobs in between chunks."""
    from tiatoolbox.models.architecture.hovernet import HoVerNet

    started = time.perf_counter()
    scale = scale or config.CELL_SCALE
    with gpu():
        model = load_hovernet(device.type)
    W, H = img.size
    # White padding so chunks at the image edge can read their context.
    pad = int(np.ceil((MARGIN + CTX) / scale)) + 2
    # The last chunk in each row/column can run a whole chunk past the edge.
    tail = int(np.ceil((CORE + MARGIN + CTX) / scale)) + 2
    padded = Image.new("RGB", (W + pad + tail, H + pad + tail), (255, 255, 255))
    padded.paste(img.convert("RGB"), (pad, pad))

    region_px = 7 * OUT + 2 * CTX  # model-scale pixels read per chunk
    points: list[tuple[int, int, int]] = []
    for cy in range(0, int(np.ceil(H * scale)), CORE):
        for cx in range(0, int(np.ceil(W * scale)), CORE):
            core_box = (cx / scale + pad, cy / scale + pad, (cx + CORE) / scale + pad, (cy + CORE) / scale + pad)
            if not _has_tissue(np.asarray(padded.crop(tuple(round(v) for v in core_box)))):
                continue
            x0, y0 = cx - MARGIN - CTX, cy - MARGIN - CTX  # model-scale origin of the read
            box = (x0 / scale + pad, y0 / scale + pad, (x0 + region_px) / scale + pad, (y0 + region_px) / scale + pad)
            region = np.asarray(padded.resize((region_px, region_px), Image.BICUBIC, box=box))
            with gpu():
                np_map, hv_map, tp_map = _predict(model, region, device)
            inst = HoVerNet._proc_np_hv(np_map, hv_map)
            info = HoVerNet.get_instance_info(inst, tp_map[..., 0].astype(np.uint8), verbose=False)
            for nuc in info.values():
                ix, iy = nuc["centroid"]  # within the 7*OUT output map
                if not (MARGIN <= ix < MARGIN + CORE and MARGIN <= iy < MARGIN + CORE):
                    continue
                gx, gy = (cx - MARGIN + ix) / scale, (cy - MARGIN + iy) / scale
                if gx < W and gy < H and nuc["type"] in TYPES:
                    points.append((int(round(gx)), int(round(gy)), int(nuc["type"])))

    counts = {name: 0 for name in TYPES.values()}
    for *_, t in points:
        counts[TYPES[t]] += 1
    total = len(points)
    # Display pixels are ~ config.UM_PER_PX microns (0.5 µm/px for a 20x photo).
    tissue_mm2 = tissue_fraction * W * H * (config.UM_PER_PX / 1000) ** 2
    return CellResult(
        total=total,
        counts=counts,
        fractions={k: round(v / total, 4) if total else 0.0 for k, v in counts.items()},
        per_mm2=round(total / tissue_mm2, 1) if tissue_mm2 > 0 else 0.0,
        tissue_mm2=round(tissue_mm2, 4),
        elapsed_ms=round((time.perf_counter() - started) * 1000),
        scale=scale,
        points=points,
    )
