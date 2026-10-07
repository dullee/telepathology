"""Tile a field-of-view photo, classify every tile, and turn the result into triage data.

The image is split into 224px tiles with 50% overlap. Each tile's class probabilities
are spread over the stride-sized cells it covers, giving a coarse probability grid
(one cell = STRIDE x STRIDE pixels). Everything downstream (heatmap, regions, score)
is derived from that grid.
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np
import torch
from PIL import Image, ImageOps
from scipy import ndimage

from app import config
from app.inference.device import describe
from app.inference.registry import KATHER, ClassSpec
from app.inference.scoring import tier_for, urgency_score


@dataclass
class Region:
    id: int
    # Bounding box in display-image pixels (x0, y0) top-left, (x1, y1) bottom-right.
    x0: int
    y0: int
    x1: int
    y1: int
    area_fraction: float
    max_prob: float
    mean_prob: float


@dataclass
class AnalysisResult:
    width: int
    height: int
    urgency: float
    tier: str
    tumor_fraction: float
    lesion_fraction: float
    max_tumor_prob: float
    largest_region_fraction: float
    necrosis_fraction: float
    tissue_fraction: float
    composition: dict[str, float]
    regions: list[Region] = field(default_factory=list)
    tiles: int = 0
    grid_shape: tuple[int, int] = (0, 0)
    device: str = ""
    elapsed_ms: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


def prepare_image(path: Path) -> Image.Image:
    """Load, honour EXIF rotation (phone photos), convert to RGB and cap the longest side."""
    img = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
    scale = config.MAX_SIDE / max(img.size)
    if scale < 1:
        img = img.resize((round(img.width * scale), round(img.height * scale)), Image.LANCZOS)
    return img


def _tile_origins(length: int) -> list[int]:
    last = max(0, length - config.TILE)
    origins = list(range(0, last + 1, config.STRIDE))
    if origins[-1] != last:
        origins.append(last)
    return origins


def _pad_to_tile(arr: np.ndarray) -> np.ndarray:
    h, w = arr.shape[:2]
    ph, pw = max(0, config.TILE - h), max(0, config.TILE - w)
    if ph or pw:
        arr = np.pad(arr, ((0, ph), (0, pw), (0, 0)), constant_values=255)
    return arr


@torch.inference_mode()
def classify_tiles(
    arr: np.ndarray, model: torch.nn.Module, device: torch.device
) -> tuple[np.ndarray, list[tuple[int, int]]]:
    """Return (N, C) softmax probabilities for every tile and its (y, x) origin."""
    origins = [(y, x) for y in _tile_origins(arr.shape[0]) for x in _tile_origins(arr.shape[1])]
    t = config.TILE
    out = []
    for i in range(0, len(origins), config.BATCH_SIZE):
        chunk = origins[i : i + config.BATCH_SIZE]
        batch = np.stack([arr[y : y + t, x : x + t] for y, x in chunk])
        # TIAToolbox kather100k preprocessing is ToTensor(): RGB scaled to [0, 1], NCHW.
        x_t = torch.from_numpy(batch).to(device).permute(0, 3, 1, 2).float().div_(255)
        if device.type == "cuda":
            with torch.autocast("cuda", dtype=torch.float16):
                probs = model(x_t)
        else:
            probs = model(x_t)
        out.append(probs.float().cpu().numpy())
    return np.concatenate(out), origins


def probability_grid(
    probs: np.ndarray, origins: list[tuple[int, int]], h: int, w: int
) -> np.ndarray:
    """Average overlapping tile predictions into a (gh, gw, C) grid of STRIDE-sized cells."""
    s = config.STRIDE
    gh, gw = -(-h // s), -(-w // s)
    acc = np.zeros((gh, gw, probs.shape[1]), np.float32)
    cnt = np.zeros((gh, gw, 1), np.float32)
    span = -(-config.TILE // s)
    for p, (y, x) in zip(probs, origins):
        cy, cx = y // s, x // s
        acc[cy : cy + span, cx : cx + span] += p
        cnt[cy : cy + span, cx : cx + span] += 1
    return acc / np.maximum(cnt, 1)


def pixel_tissue_mask(arr: np.ndarray, grid_shape: tuple[int, int]) -> np.ndarray:
    """Cells that are dark (eyepiece vignette) or blank glass are not tissue."""
    s = config.STRIDE
    gh, gw = grid_shape
    pad = np.pad(arr, ((0, gh * s - arr.shape[0]), (0, gw * s - arr.shape[1]), (0, 0)), mode="edge")
    cells = pad.reshape(gh, s, gw, s, 3).astype(np.float32)
    mean = cells.mean(axis=(1, 3, 4))
    sat = (cells.max(axis=4) - cells.min(axis=4)).mean(axis=(1, 3))
    return (mean > 40) & ~((mean > 215) & (sat < 18))


def render_heatmap(tumor: np.ndarray, tissue: np.ndarray, size: tuple[int, int]) -> Image.Image:
    """Transparent → yellow → red RGBA overlay of P(tumor), sized to the display image."""
    p = np.where(tissue, tumor, 0).astype(np.float32)
    p_img = Image.fromarray((p * 255).astype(np.uint8), "L").resize(size, Image.BILINEAR)
    p = np.asarray(p_img, np.float32) / 255
    rgba = np.zeros((*p.shape, 4), np.uint8)
    rgba[..., 0] = 255 - (35 * p).astype(np.uint8)
    rgba[..., 1] = np.clip(230 * (1 - p) ** 1.2, 0, 255).astype(np.uint8)
    rgba[..., 2] = 0
    rgba[..., 3] = (np.clip((p - 0.2) / 0.8, 0, 1) * 215).astype(np.uint8)
    return Image.fromarray(rgba, "RGBA")


def find_regions(
    tumor: np.ndarray, lesion: np.ndarray, tissue: np.ndarray, size: tuple[int, int]
) -> list[Region]:
    """Connected suspicious areas. `lesion` is P(tumor)+P(necrosis), so a necrotic core
    doesn't split a tumor in two; a component only counts if it contains tumor."""
    s = config.STRIDE
    w, h = size
    mask = (lesion >= config.TUMOR_THRESHOLD) & tissue
    labels, _ = ndimage.label(mask, structure=np.ones((3, 3)))
    tissue_cells = max(1, int(tissue.sum()))
    regions = []
    for i, sl in enumerate(ndimage.find_objects(labels), start=1):
        component = labels[sl] == i
        vals = tumor[sl][component]
        if vals.max() < config.TUMOR_THRESHOLD:
            continue
        regions.append(
            Region(
                id=0,
                x0=sl[1].start * s,
                y0=sl[0].start * s,
                x1=min(w, sl[1].stop * s),
                y1=min(h, sl[0].stop * s),
                area_fraction=round(component.sum() / tissue_cells, 4),
                max_prob=round(float(vals.max()), 3),
                mean_prob=round(float(vals.mean()), 3),
            )
        )
    regions.sort(key=lambda r: (r.area_fraction, r.max_prob), reverse=True)
    for i, r in enumerate(regions, start=1):
        r.id = i
    return regions


def analyze(
    image_path: Path, display_path: Path, heatmap_path: Path, model, device, spec: ClassSpec = KATHER
) -> AnalysisResult:
    """`spec` says which of the model's output classes are tumor / necrosis / non-tissue."""
    idx = {c: i for i, c in enumerate(spec.classes)}
    tumor_idx = [idx[c] for c in spec.tumor]
    necrosis_idx = [idx[c] for c in spec.necrosis]
    started = time.perf_counter()
    img = prepare_image(image_path)
    img.save(display_path, "JPEG", quality=90)
    arr = _pad_to_tile(np.asarray(img))

    probs, origins = classify_tiles(arr, model, device)
    grid = probability_grid(probs, origins, img.height, img.width)

    labels = grid.argmax(axis=2)
    non_tissue_idx = [idx[c] for c in spec.non_tissue]
    tissue = pixel_tissue_mask(np.asarray(img), grid.shape[:2]) & ~np.isin(labels, non_tissue_idx)
    tissue_cells = int(tissue.sum())
    # Several tumor classes (e.g. lung adenocarcinoma + squamous) add up to one P(tumor).
    tumor = grid[..., tumor_idx].sum(axis=2)
    necrotic = grid[..., necrosis_idx].sum(axis=2)

    if tissue_cells:
        tumor_fraction = float(((tumor >= config.TUMOR_THRESHOLD) & tissue).sum() / tissue_cells)
        # Smoothed so one noisy cell can't dominate the score.
        smooth = ndimage.uniform_filter(np.where(tissue, tumor, 0), size=3, mode="constant")
        max_tumor = float(smooth[tissue].max())
        necrosis = float((np.isin(labels, necrosis_idx) & tissue).sum() / tissue_cells)
        mean_probs = grid[tissue].mean(axis=0)
        composition = {
            c: round(float(v), 4)
            for c, v in zip(spec.classes, mean_probs / mean_probs.sum())
            if c not in spec.non_tissue
        }
    else:
        tumor_fraction = max_tumor = necrosis = 0.0
        composition = {}

    regions = find_regions(tumor, tumor + necrotic, tissue, img.size)
    largest = regions[0].area_fraction if regions else 0.0
    lesion_fraction = min(1.0, sum(r.area_fraction for r in regions))
    render_heatmap(tumor, tissue, img.size).save(heatmap_path, "PNG", optimize=True)

    score = urgency_score(max(tumor_fraction, lesion_fraction), max_tumor, largest, necrosis)
    return AnalysisResult(
        width=img.width,
        height=img.height,
        urgency=score,
        tier=tier_for(score),
        tumor_fraction=round(tumor_fraction, 4),
        lesion_fraction=round(lesion_fraction, 4),
        max_tumor_prob=round(max_tumor, 3),
        largest_region_fraction=largest,
        necrosis_fraction=round(necrosis, 4),
        tissue_fraction=round(tissue_cells / tissue.size, 4),
        composition=composition,
        regions=regions,
        tiles=len(origins),
        grid_shape=tissue.shape,
        device=describe(device),
        elapsed_ms=round((time.perf_counter() - started) * 1000),
    )
