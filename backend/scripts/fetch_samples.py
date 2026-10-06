"""Build demo "smartphone through the eyepiece" photos from real Kather CRC-VAL-HE-7K patches.

Only the needed patches are pulled out of the 800 MB Zenodo zip with HTTP range requests.
Each sample is a mosaic of 224px patches (0.5 µm/px, the model's native scale), with a
contiguous tumor focus of controlled size, then blurred/vignetted like a phone capture.

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
CLASSES_NEEDED = ["TUM", "DEB", "STR", "MUS", "LYM", "NORM", "MUC"]
PER_CLASS = 60


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


def tumor_mask(share: float, rng: random.Random) -> np.ndarray:
    """A single blob of roughly `share` of the grid, grown from a random seed cell."""
    mask = np.zeros((ROWS, COLS), bool)
    target = round(share * ROWS * COLS)
    if target == 0:
        return mask
    cy, cx = rng.randrange(1, ROWS - 1), rng.randrange(1, COLS - 1)
    mask[cy, cx] = True
    while mask.sum() < target:
        ys, xs = np.nonzero(mask)
        i = rng.randrange(len(ys))
        dy, dx = rng.choice([(0, 1), (1, 0), (0, -1), (-1, 0)])
        y, x = ys[i] + dy, xs[i] + dx
        if 0 <= y < ROWS and 0 <= x < COLS:
            mask[y, x] = True
    return mask


def compose(case, patches, rng: random.Random) -> Image.Image:
    _, share, necrosis, mix, *_ = case
    mask = tumor_mask(share, rng)
    canvas = Image.new("RGB", (COLS * TILE, ROWS * TILE))
    for r in range(ROWS):
        for c in range(COLS):
            if mask[r, c]:
                interior = all(
                    mask[min(ROWS - 1, max(0, r + dy)), min(COLS - 1, max(0, c + dx))]
                    for dy, dx in ((0, 1), (1, 0), (0, -1), (-1, 0))
                )
                cls = "DEB" if necrosis and interior and rng.random() < 0.45 else "TUM"
            else:
                cls = rng.choice(mix)
            canvas.paste(Image.open(rng.choice(patches[cls])), (c * TILE, r * TILE))
    return phone_capture(canvas)


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


def seed(api: str, files: list[tuple[Path, tuple]]) -> None:
    with httpx.Client(base_url=api, timeout=60) as client:
        for path, case in files:
            _, _, _, _, patient, clinic, specimen = case
            with open(path, "rb") as f:
                r = client.post(
                    "/api/cases",
                    data={"patient_ref": patient, "clinic": clinic, "specimen": specimen},
                    files={"image": (path.name, f, "image/jpeg")},
                )
            r.raise_for_status()
            print(f"  uploaded {path.name} -> case {r.json()['id']}")


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
        written.append((path, case))
        print(f"wrote {path.relative_to(ROOT)}")
    if args.seed:
        seed(args.api, written)


if __name__ == "__main__":
    main()
