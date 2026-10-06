"""Runtime configuration. Override any value with a TELEPATH_* environment variable."""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv("TELEPATH_DATA_DIR", BASE_DIR / "data"))
MEDIA_DIR = DATA_DIR / "media"
DB_URL = os.getenv("TELEPATH_DB_URL", f"sqlite:///{DATA_DIR / 'telepath.db'}")

MODEL_NAME = os.getenv("TELEPATH_MODEL", "resnet18-kather100k")
# Output index order of the TIAToolbox kather100k weights
# (tiatoolbox.models.dataset.info.KatherPatchDataset) -- not alphabetical.
CLASSES = ["BACK", "NORM", "DEB", "TUM", "ADI", "MUC", "MUS", "STR", "LYM"]
CLASS_LABELS = {
    "ADI": "Adipose",
    "BACK": "Background",
    "DEB": "Debris / necrosis",
    "LYM": "Lymphocytes",
    "MUC": "Mucus",
    "MUS": "Smooth muscle",
    "NORM": "Normal mucosa",
    "STR": "Stroma",
    "TUM": "Tumor epithelium",
}
NON_TISSUE = {"ADI", "BACK"}

TILE = 224
STRIDE = int(os.getenv("TELEPATH_STRIDE", 112))
BATCH_SIZE = int(os.getenv("TELEPATH_BATCH", 64))
# Longest image side is resized to this before tiling (eyepiece photos are often 4000px+).
MAX_SIDE = int(os.getenv("TELEPATH_MAX_SIDE", 2048))
MAX_UPLOAD_BYTES = 40 * 1024 * 1024

# A tile is "suspicious" when P(tumor) exceeds this.
TUMOR_THRESHOLD = 0.5
# Urgency = 100 * weighted sum (see scoring.py).
URGENCY_WEIGHTS = {"tumor_fraction": 0.5, "max_tumor_prob": 0.3, "largest_region": 0.2}
NECROSIS_BONUS = 10.0
TIERS = [(70.0, "critical"), (40.0, "high"), (0.0, "routine")]
