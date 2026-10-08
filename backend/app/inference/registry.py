"""Selectable tile classifiers.

Every profile produces a model that takes NCHW RGB tiles scaled to [0, 1] and returns
softmax probabilities over its `ClassSpec.classes`. The spec tells the engine which classes
count as tumor, necrosis and non-tissue, so heatmaps, regions and scoring work for any organ.

- "cnn": a TIAToolbox pretrained patch classifier (colorectal, Kather 9 classes), used as-is.
- "foundation": a pathology foundation model (feature extractor) plus a small linear head
  trained on its embeddings with `scripts/train_head.py`, stored under `inference/heads/`.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

from app import config

HEADS_DIR = Path(__file__).resolve().parent / "heads"


@dataclass(frozen=True)
class ClassSpec:
    classes: tuple[str, ...]  # model output order
    labels: dict[str, str]
    tumor: tuple[str, ...]  # summed into P(tumor) for the heatmap, regions and score
    necrosis: tuple[str, ...] = ()
    non_tissue: tuple[str, ...] = ()


KATHER = ClassSpec(
    classes=tuple(config.CLASSES),
    labels=config.CLASS_LABELS,
    tumor=("TUM",),
    necrosis=("DEB",),
    non_tissue=tuple(sorted(config.NON_TISSUE)),
)
GASTRIC = ClassSpec(
    classes=("ADI", "DEB", "LYM", "MUC", "MUS", "NOR", "STR", "TUM"),
    labels={
        "ADI": "Adipose",
        "DEB": "Debris / necrosis",
        "LYM": "Lymphocytes",
        "MUC": "Mucus",
        "MUS": "Smooth muscle",
        "NOR": "Normal gastric mucosa",
        "STR": "Stroma",
        "TUM": "Tumor (gastric adenocarcinoma)",
    },
    tumor=("TUM",),
    necrosis=("DEB",),
    non_tissue=("ADI",),
)
LIVER = ClassSpec(
    classes=("TUM", "FIB", "INF", "NEC", "NOR", "REA", "STE"),
    labels={
        "TUM": "Tumor (hepatocellular carcinoma)",
        "FIB": "Fibrosis",
        "INF": "Inflammation",
        "NEC": "Necrosis",
        "NOR": "Normal liver",
        "REA": "Bile duct reaction",
        "STE": "Steatosis",
    },
    tumor=("TUM",),
    necrosis=("NEC",),
)
LUNG = ClassSpec(
    classes=("NOR", "ACA", "SCC"),
    labels={
        "NOR": "Normal lung",
        "ACA": "Adenocarcinoma",
        "SCC": "Squamous cell carcinoma",
    },
    tumor=("ACA", "SCC"),
)


@dataclass(frozen=True)
class ModelProfile:
    id: str
    label: str
    organ: str  # shown as the group heading in the model picker
    family: str  # "cnn" | "foundation"
    description: str
    license: str
    params: str
    speed: str  # rough relative cost per tile: "fast" | "medium" | "slow"
    spec: ClassSpec = KATHER
    tiatoolbox_name: str = ""
    hf_repo: str = ""
    # Backbone input normalisation (applied after scaling to [0, 1]).
    mean: tuple[float, float, float] = (0.0, 0.0, 0.0)
    std: tuple[float, float, float] = (1.0, 1.0, 1.0)
    # Centre-crop each 224px tile to this many pixels (then resize back to 224) so the field of
    # view matches the training patches, e.g. 150px liver patches. 0 = use the whole tile.
    crop_px: int = 0
    download_gb: float = 0.0
    trained_on: str = ""

    @property
    def head_path(self) -> Path:
        return HEADS_DIR / f"{self.id}.pt"

    def availability(self) -> tuple[bool, str]:
        if self.family == "foundation" and not self.head_path.exists():
            return False, f"Classifier head not trained yet: run scripts/train_head.py --model {self.id}"
        return True, ""

    def weights_cached(self) -> bool:
        if not self.hf_repo:
            return True  # TIAToolbox weights are small and fetched on first load
        from huggingface_hub import try_to_load_from_cache

        return isinstance(try_to_load_from_cache(self.hf_repo, "model.safetensors"), str)

    def head_metrics(self) -> dict:
        """Validation accuracy recorded by train_head.py, if the head exists."""
        if self.family != "foundation" or not self.head_path.exists():
            return {}
        import torch

        ckpt = torch.load(self.head_path, map_location="cpu", weights_only=True)
        return {k: ckpt[k] for k in ("val_accuracy", "val_accuracy_degraded") if k in ckpt}

    def to_dict(self) -> dict:
        ok, reason = self.availability()
        data = asdict(self)
        data.pop("spec")
        data.update(
            classes=self.spec.labels,
            tumor_classes=list(self.spec.tumor),
            available=ok,
            unavailable_reason=reason,
            weights_cached=self.weights_cached(),
            validation=self.head_metrics(),
        )
        return data


def _midnight(id: str, organ: str, spec: ClassSpec, description: str, trained_on: str, **kw) -> ModelProfile:
    return ModelProfile(
        id=id,
        label=f"Midnight-12k · {organ}",
        organ=organ,
        family="foundation",
        description=description,
        license="MIT model · CC-BY 4.0 data",
        params="1.1B",
        speed="slow",
        spec=spec,
        hf_repo="kaiko-ai/midnight",
        mean=(0.5, 0.5, 0.5),
        std=(0.5, 0.5, 0.5),
        download_gb=4.5,
        trained_on=trained_on,
        **kw,
    )


_TIATOOLBOX = "TIAToolbox (BSD-3)"

PROFILES: dict[str, ModelProfile] = {
    p.id: p
    for p in [
        ModelProfile(
            id="resnet18-kather100k",
            label="ResNet-18 · Kather100k",
            organ="Colorectal",
            family="cnn",
            description="Default. Small colorectal tissue classifier; runs well on CPU.",
            license=_TIATOOLBOX,
            params="11M",
            speed="fast",
            tiatoolbox_name="resnet18-kather100k",
        ),
        ModelProfile(
            id="mobilenet_v3_large-kather100k",
            label="MobileNet-V3 · Kather100k",
            organ="Colorectal",
            family="cnn",
            description="Lightest option for clinic PCs without a GPU.",
            license=_TIATOOLBOX,
            params="5M",
            speed="fast",
            tiatoolbox_name="mobilenet_v3_large-kather100k",
        ),
        ModelProfile(
            id="wide_resnet50_2-kather100k",
            label="Wide ResNet-50 · Kather100k",
            organ="Colorectal",
            family="cnn",
            description="Larger CNN, same colorectal classes; more accurate than ResNet-18.",
            license=_TIATOOLBOX,
            params="67M",
            speed="medium",
            tiatoolbox_name="wide_resnet50_2-kather100k",
        ),
        _midnight(
            "midnight-kather100k",
            "Colorectal",
            KATHER,
            "Foundation model with a colorectal head (9 tissue classes). Most robust to stain, "
            "blur and phone-camera shifts.",
            "Kather NCT-CRC-HE-100K",
        ),
        _midnight(
            "midnight-gastric",
            "Stomach",
            GASTRIC,
            "Gastric biopsies: tumor vs normal mucosa, stroma, muscle, lymphocytes, mucus, necrosis.",
            "HMU-GC-HE-30K (Harbin Medical University, 300 slides)",
        ),
        _midnight(
            "midnight-liver",
            "Liver",
            LIVER,
            "Liver biopsies: hepatocellular carcinoma vs normal liver, fibrosis, inflammation, "
            "necrosis, steatosis, bile duct reaction.",
            "HepatoBench (20×, 150px patches)",
            crop_px=150,
        ),
        _midnight(
            "midnight-lung",
            "Lung",
            LUNG,
            "Lung biopsies: adenocarcinoma and squamous cell carcinoma vs normal lung.",
            "LungHist700 (45 patients, microscope-camera images)",
        ),
    ]
}

DEFAULT_ID = "resnet18-kather100k"


def get_profile(model_id: str) -> ModelProfile:
    if model_id in PROFILES:
        return PROFILES[model_id]
    # Any other TIAToolbox Kather100k backbone (e.g. densenet161-kather100k) shares the
    # same classes and preprocessing, so it can be used without a curated entry.
    if model_id.endswith("-kather100k"):
        return ModelProfile(
            id=model_id,
            label=model_id,
            organ="Colorectal",
            family="cnn",
            description="TIAToolbox Kather100k classifier.",
            license=_TIATOOLBOX,
            params="",
            speed="medium",
            tiatoolbox_name=model_id,
        )
    raise KeyError(f"Unknown model '{model_id}'. Choose one of: {', '.join(PROFILES)}")
