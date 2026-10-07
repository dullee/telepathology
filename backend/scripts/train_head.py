"""Train an organ-specific head for a foundation-model profile (linear probe on frozen embeddings).

Each profile has a dataset loader below that returns labelled train/val patches in the profile's class
order. Every training patch is embedded twice: once clean, and once degraded the way a phone photo
through an eyepiece is (blur, colour cast, noise, JPEG), so the head learns to ignore those effects.
Validation is reported on clean and degraded patches.

  midnight-kather100k  Kather NCT-CRC-HE-100K -> CRC-VAL-HE-7K (different patients), + ResNet-18 baseline
  midnight-gastric     HMU-GC-HE-30K (figshare 10.6084/m9.figshare.25954813)
  midnight-liver       HepatoBench (huggingface.co/datasets/xtxx/HepatoBench)
  midnight-lung        LungHist700 (figshare 10.6084/m9.figshare.25459174), split by patient

The gastric and liver releases have no patient IDs. For those, val takes the highest-numbered 20% of
each class's patches, on the assumption that numbering follows slide order. Leakage between splits
can't be ruled out, so treat those accuracies as optimistic.

Patches are fetched with HTTP range requests where possible, so only the sampled files are downloaded.

    uv run python scripts/train_head.py --model midnight-gastric
    uv run python scripts/train_head.py --model midnight-lung --per-class 400
"""

from __future__ import annotations

import argparse
import csv
import io
import random
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image, ImageFilter
from remotezip import RemoteIOError, RemoteZip

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import config  # noqa: E402
from app.inference.device import pick_device  # noqa: E402
from app.inference.foundation import FoundationEmbedder, fit_input, load_backbone  # noqa: E402
from app.inference.registry import ModelProfile, get_profile  # noqa: E402

CACHE = ROOT / "data" / "heads_train"
Items = list[tuple[Path, int]]


# --------------------------------------------------------------------------- fetching


def retry(fn):
    """Zenodo/figshare answer bursts of range requests with 429; back off and try again."""
    for attempt in range(6):
        try:
            return fn()
        except RemoteIOError:
            time.sleep(5 * 2**attempt)
    raise RuntimeError("The server kept refusing requests; try again later")


def pull_from_zip(url: str, wanted: list[tuple[str, Path]]) -> None:
    """Extract the (member, dest) pairs not cached yet, two range readers at a time."""
    todo = [(n, d) for n, d in wanted if not d.exists()]
    if not todo:
        return
    print(f"  fetching {len(todo)} patches from {url.split('?')[0].rsplit('/', 1)[-1]}")
    for _, d in todo:
        d.parent.mkdir(parents=True, exist_ok=True)

    def worker(chunk):
        with retry(lambda: RemoteZip(url)) as z:
            for n, dest in chunk:
                data = retry(lambda: z.read(n))
                Image.open(io.BytesIO(data)).convert("RGB").save(dest)

    # More than a couple of parallel range readers gets rate-limited.
    with ThreadPoolExecutor(2) as pool:
        list(pool.map(worker, [todo[i::2] for i in range(2)]))


def zip_names(url: str) -> list[str]:
    return [n for n in retry(lambda: RemoteZip(url).namelist()) if re.search(r"\.(tif|png|jpe?g)$", n, re.I)]


def index_split(names: list[str], per_class: int, val_per_class: int, rng: random.Random):
    """No patient IDs: train from the lowest-numbered 80%, val from the highest-numbered 20%."""
    names = sorted(names, key=lambda n: int(re.findall(r"\d+", Path(n).stem)[-1]))
    cut = int(len(names) * 0.8)
    return rng.sample(names[:cut], min(per_class, cut)), rng.sample(names[cut:], min(val_per_class, len(names) - cut))


def kather(profile: ModelProfile, per_class: int, val_per_class: int) -> tuple[Items, Items]:
    url = "https://zenodo.org/records/1214456/files/{}.zip?download=1"
    out: list[Items] = []
    for split, zname, n, seed in (("train", "NCT-CRC-HE-100K", per_class, 1), ("val", "CRC-VAL-HE-7K", val_per_class, 2)):
        rng, items, wanted = random.Random(seed), [], []
        names = zip_names(url.format(zname))
        for ci, cls in enumerate(profile.spec.classes):
            pool = sorted(m for m in names if f"/{cls}/" in m)
            for m in rng.sample(pool, min(n, len(pool))):
                dest = ROOT / "data" / "kather_head" / split / cls / (Path(m).stem + ".png")
                wanted.append((m, dest))
                items.append((dest, ci))
        pull_from_zip(url.format(zname), wanted)
        out.append(items)
    return out[0], out[1]


def gastric(profile: ModelProfile, per_class: int, val_per_class: int) -> tuple[Items, Items]:
    url = "https://ndownloader.figshare.com/files/46765759"  # HMU-GC-HE-30K.zip
    names, rng = zip_names(url), random.Random(3)
    train, val, wanted = [], [], []
    for ci, cls in enumerate(profile.spec.classes):
        tr, va = index_split([n for n in names if f"/{cls}/" in n], per_class, val_per_class, rng)
        for split, members, items in (("train", tr, train), ("val", va, val)):
            for m in members:
                dest = CACHE / "gastric" / split / cls / Path(m).name
                wanted.append((m, dest))
                items.append((dest, ci))
    pull_from_zip(url, wanted)
    return train, val


def liver(profile: ModelProfile, per_class: int, val_per_class: int) -> tuple[Items, Items]:
    base = "https://huggingface.co/datasets/xtxx/HepatoBench/resolve/main/"
    zips = {"TUM": "01_TUM", "FIB": "02_FIB", "INF": "03_INF", "NEC": "04_NEC", "NOR": "05_NOR", "REA": "06_REA", "STE": "07_STE"}
    rng = random.Random(4)
    train, val = [], []
    for ci, cls in enumerate(profile.spec.classes):
        url = base + zips[cls] + ".zip"
        tr, va = index_split(zip_names(url), per_class, val_per_class, rng)
        wanted = []
        for split, members, items in (("train", tr, train), ("val", va, val)):
            for m in members:
                dest = CACHE / "liver" / split / cls / Path(m).name
                wanted.append((m, dest))
                items.append((dest, ci))
        pull_from_zip(url, wanted)
    return train, val


def lung(profile: ModelProfile, per_class: int, val_per_class: int) -> tuple[Items, Items]:
    """LungHist700 whole microscope-camera images -> 224px tiles at ~0.5 µm/px, split by patient."""
    root = ROOT / "data" / "lunghist700"
    rar = root / "LungHist700.rar"
    if not (root / "data" / "data.csv").exists():
        if not rar.exists():
            print("  downloading LungHist700.rar (670 MB)")
            subprocess.run(["curl", "-sL", "-C", "-", "-o", str(rar), "https://ndownloader.figshare.com/files/45206104"], check=True)
        subprocess.run(["bsdtar", "-xf", str(rar), "-C", str(root)], check=True)
    rows = list(csv.DictReader(open(root / "data" / "data.csv")))
    code = {"nor": "NOR", "aca": "ACA", "scc": "SCC"}

    # Hold out ~20% of each class's images, choosing whole patients.
    rng = random.Random(5)
    val_patients: set[str] = set()
    for sup in code:
        patients = sorted({r["patient_id"] for r in rows if r["superclass"] == sup})
        rng.shuffle(patients)
        total = sum(r["superclass"] == sup for r in rows)
        held = sum(r["superclass"] == sup and r["patient_id"] in val_patients for r in rows)
        for p in patients:
            if held >= 0.2 * total:
                break
            if p not in val_patients:
                val_patients.add(p)
                held += sum(r["superclass"] == sup and r["patient_id"] == p for r in rows)

    tiles: dict[tuple[str, str], list[Path]] = {}
    for r in rows:
        folder = r["superclass"] + (f"_{r['subclass']}" if r["subclass"] else "")
        src = root / "data" / "images" / folder / f"{folder}_{r['resolution']}_{r['image_id']}.jpg"
        split = "val" if r["patient_id"] in val_patients else "train"
        out_dir = CACHE / "lung" / split / code[r["superclass"]]
        key = (split, code[r["superclass"]])
        tiles.setdefault(key, []).extend(tile_image(src, out_dir, r))
    print(f"  lung: {len(val_patients)} of {len({r['patient_id'] for r in rows})} patients held out for val")

    train, val = [], []
    for ci, cls in enumerate(profile.spec.classes):
        for split, n, items in (("train", per_class, train), ("val", val_per_class, val)):
            pool = sorted(tiles.get((split, cls), []))
            items += [(p, ci) for p in rng.sample(pool, min(n, len(pool)))]
    return train, val


def tile_image(src: Path, out_dir: Path, row: dict) -> list[Path]:
    """Cut 224px tissue tiles; 40x images are halved first so every tile is ~20x scale."""
    stem = f"p{row['patient_id']}_{src.stem}"
    done = sorted(out_dir.glob(f"{stem}_*.png"))
    if done or (out_dir / f"{stem}.none").exists():
        return done
    out_dir.mkdir(parents=True, exist_ok=True)
    img = Image.open(src).convert("RGB")
    if row["resolution"] == "40x":
        img = img.resize((img.width // 2, img.height // 2), Image.LANCZOS)
    arr = np.asarray(img)
    t, out = config.TILE, []
    for y in range(0, arr.shape[0] - t + 1, t):
        for x in range(0, arr.shape[1] - t + 1, t):
            tile = arr[y : y + t, x : x + t].astype(np.float32)
            sat = (tile.max(axis=2) - tile.min(axis=2)).mean()
            if tile.mean() < 215 and sat > 25:  # skip blank glass / alveolar air
                p = out_dir / f"{stem}_{y}_{x}.png"
                Image.fromarray(tile.astype(np.uint8)).save(p)
                out.append(p)
    if not out:
        (out_dir / f"{stem}.none").touch()
    return out


DATASETS = {"midnight-kather100k": kather, "midnight-gastric": gastric, "midnight-liver": liver, "midnight-lung": lung}


# --------------------------------------------------------------------------- training


def degrade(img: Image.Image, rng: random.Random) -> Image.Image:
    """Approximate a smartphone capture through the eyepiece."""
    img = img.filter(ImageFilter.GaussianBlur(rng.uniform(0.3, 1.6)))
    arr = np.asarray(img, np.float32)
    arr = arr * np.array([rng.uniform(0.92, 1.08) for _ in range(3)]) * rng.uniform(0.85, 1.1)
    arr += np.random.default_rng(rng.randrange(1 << 30)).normal(0, rng.uniform(0, 5), arr.shape)
    img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=rng.randint(55, 90))
    return Image.open(buf).convert("RGB")


def to_batch(imgs: list[Image.Image], device: torch.device) -> torch.Tensor:
    """Native-size patches -> [0, 1] NCHW at TILE px, resized exactly as at inference."""
    x = torch.from_numpy(np.stack([np.asarray(im) for im in imgs])).to(device).permute(0, 3, 1, 2).float().div_(255)
    return fit_input(x)


@torch.inference_mode()
def run(model, items, device, *, degraded: bool, batch: int, seed: int, desc: str) -> torch.Tensor:
    rng = random.Random(seed)
    out, started = [], time.perf_counter()
    for i in range(0, len(items), batch):
        imgs = [Image.open(p).convert("RGB") for p, _ in items[i : i + batch]]
        if degraded:
            imgs = [degrade(im, rng) for im in imgs]
        out.append(model(to_batch(imgs, device)).float().cpu())
        done = min(i + batch, len(items))
        rate = done / (time.perf_counter() - started)
        print(f"\r  {desc}: {done}/{len(items)} ({rate:.1f} tiles/s)", end="", flush=True)
    print()
    return torch.cat(out)


def embed_cached(name, embedder, items, device, args, *, degraded, seed) -> torch.Tensor:
    path = CACHE / "embeddings" / f"{args.model}-{name}-{len(items)}.pt"
    if path.exists():
        return torch.load(path, weights_only=True)
    feats = run(embedder, items, device, degraded=degraded, batch=args.batch, seed=seed, desc=name)
    path.parent.mkdir(parents=True, exist_ok=True)
    torch.save(feats, path)
    return feats


def train_linear(x: torch.Tensor, y: torch.Tensor, n_classes: int, epochs: int, wd: float):
    """Class-balanced multinomial logistic regression on standardised features,
    folded back to raw-feature weights."""
    mu, sigma = x.mean(0), x.std(0).clamp_min(1e-6)
    xs = (x - mu) / sigma
    weights = len(y) / (n_classes * torch.bincount(y, minlength=n_classes).clamp_min(1).float())
    head = torch.nn.Linear(x.shape[1], n_classes)
    opt = torch.optim.AdamW(head.parameters(), lr=1e-3, weight_decay=wd)
    gen = torch.Generator().manual_seed(0)
    for _ in range(epochs):
        for idx in torch.randperm(len(xs), generator=gen).split(256):
            loss = F.cross_entropy(head(xs[idx]), y[idx], weight=weights, label_smoothing=0.05)
            opt.zero_grad()
            loss.backward()
            opt.step()
    w = head.weight.detach() / sigma
    b = head.bias.detach() - w @ mu
    return w, b


def report(name: str, probs: torch.Tensor, y: torch.Tensor, classes, tumor_idx) -> dict:
    pred = probs.argmax(1)
    acc = (pred == y).float().mean().item()
    per = " ".join(f"{c}={(pred[y == i] == i).float().mean().item():.2f}" for i, c in enumerate(classes) if (y == i).any())
    # Triage view: is a tumor tile called tumor (any tumor class), and normal tissue not?
    is_tum, called_tum = torch.isin(y, tumor_idx), torch.isin(pred, tumor_idx)
    sens = (called_tum & is_tum).sum().item() / max(1, is_tum.sum().item())
    spec = (~called_tum & ~is_tum).sum().item() / max(1, (~is_tum).sum().item())
    print(f"  {name:<36} acc={acc:.3f}  tumor sens={sens:.3f} spec={spec:.3f}\n      {per}")
    return {"acc": round(acc, 4), "tumor_sensitivity": round(sens, 4), "tumor_specificity": round(spec, 4)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="midnight-kather100k", choices=sorted(DATASETS))
    ap.add_argument("--per-class", type=int, default=250)
    ap.add_argument("--val-per-class", type=int, default=100)
    ap.add_argument("--batch", type=int, default=16)
    ap.add_argument("--epochs", type=int, default=60)
    ap.add_argument("--weight-decay", type=float, default=1e-2)
    ap.add_argument("--no-baseline", action="store_true", help="skip the ResNet-18 comparison (colorectal)")
    args = ap.parse_args()

    profile = get_profile(args.model)
    classes = list(profile.spec.classes)
    tumor_idx = torch.tensor([classes.index(c) for c in profile.spec.tumor])
    device = pick_device()
    print(f"Preparing {profile.id} data ({profile.trained_on})...")
    train, val = DATASETS[profile.id](profile, args.per_class, args.val_per_class)
    counts = {c: sum(1 for _, i in train if i == k) for k, c in enumerate(classes)}
    print(f"  train {len(train)} {counts} | val {len(val)}")
    y_train = torch.tensor([c for _, c in train] * 2)
    y_val = torch.tensor([c for _, c in val])

    print(f"Loading {profile.hf_repo} on {device}...")
    embedder = FoundationEmbedder(load_backbone(profile, device), profile).to(device).eval()
    x_train = torch.cat([
        embed_cached("train-clean", embedder, train, device, args, degraded=False, seed=0),
        embed_cached("train-degraded", embedder, train, device, args, degraded=True, seed=1),
    ])
    x_val = embed_cached("val-clean", embedder, val, device, args, degraded=False, seed=0)
    x_val_deg = embed_cached("val-degraded", embedder, val, device, args, degraded=True, seed=2)
    del embedder

    w, b = train_linear(x_train, y_train, len(classes), args.epochs, args.weight_decay)
    print(f"\nValidation, {len(val)} held-out patches:")
    clean = report(f"{profile.id} clean", torch.softmax(x_val @ w.T + b, 1), y_val, classes, tumor_idx)
    deg = report(f"{profile.id} phone-degraded", torch.softmax(x_val_deg @ w.T + b, 1), y_val, classes, tumor_idx)

    if profile.id == "midnight-kather100k" and not args.no_baseline:
        from tiatoolbox.models.architecture import get_pretrained_model

        cnn, _ = get_pretrained_model("resnet18-kather100k")
        cnn = cnn.to(device).eval()
        for name, degraded in (("clean", False), ("phone-degraded", True)):
            probs = run(cnn, val, device, degraded=degraded, batch=64, seed=2 if degraded else 0, desc="baseline")
            report(f"resnet18-kather100k {name}", probs, y_val, classes, tumor_idx)

    profile.head_path.parent.mkdir(parents=True, exist_ok=True)
    torch.save(
        {
            "weight": w.contiguous(),
            "bias": b.contiguous(),
            "classes": classes,
            "backbone": profile.hf_repo,
            "trained_on": profile.trained_on,
            "train_patches": len(train),
            "val_patches": len(val),
            "val_accuracy": clean["acc"],
            "val_accuracy_degraded": deg["acc"],
            "val_tumor_sensitivity_degraded": deg["tumor_sensitivity"],
            "val_tumor_specificity_degraded": deg["tumor_specificity"],
        },
        profile.head_path,
    )
    print(f"\nSaved {profile.head_path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
