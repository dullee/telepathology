"""Build demo "smartphone through the eyepiece" photos from real Kather CRC-VAL-HE-7K patches.

Only the needed patches are pulled out of the 800 MB Zenodo zip with HTTP range requests.
Each sample is a mosaic of 224px patches (0.5 µm/px, the model's native scale), with a
contiguous tumor focus of controlled size, then blurred/vignetted like a phone capture.

Stitched cases photograph a larger slide as a grid of overlapping eyepiece fields (about a
third overlap, slight rotation and exposure drift between shots, like moving the stage by
hand). They are uploaded as several photos so the server stitches them (samples/<name>/).

    uv run python scripts/fetch_samples.py            # writes samples/*.jpg
    uv run python scripts/fetch_samples.py --seed     # ...and uploads them to the running API
"""

from __future__ import annotations

import argparse
import io
import random
from pathlib import Path

import httpx
import numpy as np
from PIL import Image, ImageFilter
from remotezip import RemoteZip

ZIP_URL = "https://zenodo.org/records/1214456/files/CRC-VAL-HE-7K.zip?download=1"
ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "data" / "kather_patches"
OUT = ROOT / "samples"
TILE = 224
COLS, ROWS = 8, 6

# (name, tumor share, necrosis inside tumor, background mix, patient, clinic, specimen)
CASES = [
    ("advanced_adenocarcinoma", 0.62, True, ["STR", "MUS", "LYM"], "KE-0412", "Kisumu Rural Health Centre", "Colon biopsy"),
    ("invasive_focus", 0.38, False, ["STR", "NORM", "MUS"], "KE-0398", "Busia Sub-County Clinic", "Rectal biopsy"),
    ("small_suspicious_focus", 0.12, False, ["NORM", "STR", "MUC"], "UG-1187", "Mbale Field Clinic", "Colon polyp"),
    ("inflamed_mucosa", 0.0, False, ["NORM", "LYM", "STR"], "TZ-0033", "Moshi Outreach Unit", "Colon biopsy"),
    ("normal_mucosa", 0.0, False, ["NORM", "NORM", "MUC", "STR"], "KE-0420", "Kisumu Rural Health Centre", "Screening biopsy"),
    ("mucinous_lesion", 0.25, False, ["MUC", "STR", "NORM"], "UG-1201", "Gulu Community Hospital", "Colon biopsy"),
]
# Stitched cases: (name, tumor share, necrosis, mix, patient, clinic, specimen,
#                  slide size in patches (cols, rows), field grid (cols, rows), blurry photo index or None)
MOSAIC_CASES = [
    ("mosaic_large_tumor", 0.45, True, ["STR", "MUS", "LYM"], "KE-0431", "Kisumu Rural Health Centre",
     "Colon resection margin (9 photos)", (12, 9), (3, 3), None),
    ("mosaic_benign_mucosa", 0.0, False, ["NORM", "NORM", "MUC", "STR", "LYM"], "UG-1215", "Mbale Field Clinic",
     "Colon biopsy (6 photos)", (12, 7), (3, 2), None),
    ("mosaic_one_blurry_photo", 0.2, False, ["NORM", "STR", "MUS"], "TZ-0051", "Moshi Outreach Unit",
     "Rectal biopsy (6 photos, 1 out of focus)", (12, 7), (3, 2), 4),
]
CLASSES_NEEDED = ["TUM", "DEB", "STR", "MUS", "LYM", "NORM", "MUC"]
PER_CLASS = 80  # stitched slides use each patch at most once


def fetch_patches() -> dict[str, list[Path]]:
    CACHE.mkdir(parents=True, exist_ok=True)
    have = {c: sorted((CACHE / c).glob("*.png")) for c in CLASSES_NEEDED}
    if all(len(v) >= PER_CLASS for v in have.values()):
        return have
    print("Fetching Kather CRC-VAL-HE-7K patches from Zenodo (range requests)...")
    rng = random.Random(7)
    with RemoteZip(ZIP_URL) as z:
        names = [n for n in z.namelist() if n.lower().endswith(".tif")]
        for cls in CLASSES_NEEDED:
            if len(have[cls]) >= PER_CLASS:
                continue
            pool = [n for n in names if f"/{cls}/" in n]
            (CACHE / cls).mkdir(exist_ok=True)
            for n in rng.sample(pool, min(PER_CLASS, len(pool))):
                dest = CACHE / cls / (Path(n).stem + ".png")
                if not dest.exists():
                    Image.open(io.BytesIO(z.read(n))).convert("RGB").save(dest)
            have[cls] = sorted((CACHE / cls).glob("*.png"))
            print(f"  {cls}: {len(have[cls])} patches")
    return have


def tumor_mask(share: float, rng: random.Random, rows: int = ROWS, cols: int = COLS) -> np.ndarray:
    """A single blob of roughly `share` of the grid, grown from a random seed cell."""
    mask = np.zeros((rows, cols), bool)
    target = round(share * rows * cols)
    if target == 0:
        return mask
    cy, cx = rng.randrange(1, rows - 1), rng.randrange(1, cols - 1)
    mask[cy, cx] = True
    while mask.sum() < target:
        ys, xs = np.nonzero(mask)
        i = rng.randrange(len(ys))
        dy, dx = rng.choice([(0, 1), (1, 0), (0, -1), (-1, 0)])
        y, x = ys[i] + dy, xs[i] + dx
        if 0 <= y < rows and 0 <= x < cols:
            mask[y, x] = True
    return mask


def compose(case, patches, rng: random.Random, cols: int = COLS, rows: int = ROWS, capture: bool = True) -> Image.Image:
    """`capture=False` builds a larger slide for stitching. Its patches are drawn without
    replacement: a patch repeated elsewhere on the slide would give the stitcher false matches
    between photos that don't overlap (real tissue never repeats exactly)."""
    _, share, necrosis, mix, *_ = case
    mask = tumor_mask(share, rng, rows, cols)
    pools = {c: rng.sample(v, len(v)) for c, v in patches.items()}

    def pick(cls: str) -> Path:
        if capture:
            return rng.choice(patches[cls])
        if not pools[cls]:
            raise SystemExit(f"Not enough distinct {cls} patches for a stitched slide; raise PER_CLASS")
        return pools[cls].pop()

    canvas = Image.new("RGB", (cols * TILE, rows * TILE))
    for r in range(rows):
        for c in range(cols):
            if mask[r, c]:
                interior = all(
                    mask[min(rows - 1, max(0, r + dy)), min(cols - 1, max(0, c + dx))]
                    for dy, dx in ((0, 1), (1, 0), (0, -1), (-1, 0))
                )
                cls = "DEB" if necrosis and interior and rng.random() < 0.45 else "TUM"
            else:
                cls = rng.choice(mix)
            canvas.paste(Image.open(pick(cls)), (c * TILE, r * TILE))
    return phone_capture(canvas) if capture else canvas


def capture_fields(slide: Image.Image, grid: tuple[int, int], rng: random.Random, blurry: int | None) -> list[Image.Image]:
    """Photograph `slide` as a grid of 4:3 eyepiece fields overlapping by about a third."""
    gc, gr = grid
    fw = round(slide.width / (1 + (gc - 1) * 2 / 3))  # field width so neighbours overlap by 1/3
    fh = round(fw * 3 / 4)
    xs = np.linspace(0, slide.width - fw, gc).round().astype(int)
    ys = np.linspace(0, slide.height - fh, gr).round().astype(int)
    fields = []
    for y in ys:
        for x in xs:
            # Hand-moved stage: a little jitter and rotation; lamp/auto-exposure drift.
            jx, jy = rng.randint(-20, 20), rng.randint(-20, 20)
            box = (max(0, x + jx), max(0, y + jy), min(slide.width, x + jx + fw), min(slide.height, y + jy + fh))
            field = slide.crop(box).rotate(rng.uniform(-3, 3), Image.BICUBIC, fillcolor=(0, 0, 0))
            arr = np.asarray(field, np.float32) * rng.uniform(0.9, 1.1)
            field = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))
            if len(fields) == blurry:
                field = field.filter(ImageFilter.GaussianBlur(4))
            fields.append(phone_capture(field))
    return fields


def phone_capture(img: Image.Image) -> Image.Image:
    """Soft focus, warm lamp tint and the circular field stop of a microscope eyepiece."""
    img = img.filter(ImageFilter.GaussianBlur(0.8))
    arr = np.asarray(img, np.float32)
    arr *= np.array([1.03, 1.0, 0.95])
    h, w = arr.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w]
    d = np.hypot((xx - w / 2) / (w / 2), (yy - h / 2) / (w / 2))
    falloff = np.clip((1.08 - d) / 0.12, 0, 1)[..., None]
    arr = arr * falloff * (1 - 0.18 * d[..., None] ** 2)
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))


def seed(api: str, files: list[tuple[list[Path], tuple]]) -> None:
    with httpx.Client(base_url=api, timeout=120) as client:
        for paths, case in files:
            patient, clinic, specimen = case[4:7]
            form = {"patient_ref": patient, "clinic": clinic, "specimen": specimen}
            if len(paths) == 1:
                upload = [("image", (paths[0].name, paths[0].read_bytes(), "image/jpeg"))]
            else:
                upload = [("images", (p.name, p.read_bytes(), "image/jpeg")) for p in paths]
            r = client.post("/api/cases", data=form, files=upload)
            r.raise_for_status()
            print(f"  uploaded {paths[0].parent.name if len(paths) > 1 else paths[0].name} -> case {r.json()['id']}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", action="store_true", help="upload samples to the API")
    ap.add_argument("--api", default="http://localhost:8000")
    args = ap.parse_args()

    patches = fetch_patches()
    OUT.mkdir(exist_ok=True)
    rng = random.Random(42)
    written = []
    for case in CASES:
        path = OUT / f"{case[0]}.jpg"
        compose(case, patches, rng).save(path, "JPEG", quality=88)
        written.append(([path], case))
        print(f"wrote {path.relative_to(ROOT)}")
    for case in MOSAIC_CASES:
        (cols, rows), grid, blurry = case[7], case[8], case[9]
        slide = compose(case, patches, rng, cols, rows, capture=False)
        folder = OUT / case[0]
        folder.mkdir(exist_ok=True)
        for old in folder.glob("*.jpg"):
            old.unlink()
        paths = []
        for i, field in enumerate(capture_fields(slide, grid, rng, blurry), start=1):
            paths.append(folder / f"photo_{i:02d}.jpg")
            field.save(paths[-1], "JPEG", quality=88)
        written.append((paths, case))
        print(f"wrote {folder.relative_to(ROOT)}/ ({len(paths)} photos)")
    if args.seed:
        seed(args.api, written)


if __name__ == "__main__":
    main()
