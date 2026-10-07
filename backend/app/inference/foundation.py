"""Pathology foundation model + linear head, wrapped to behave like a TIAToolbox classifier."""

from __future__ import annotations

import torch
import torch.nn.functional as F
from torch import nn

from app import config
from app.inference.registry import ModelProfile


def backbone_dtype(device: torch.device) -> torch.dtype:
    # fp16 halves memory (a 1.1B ViT is ~2.3 GB instead of 4.5 GB), which is what lets it
    # fit beside the OS on an 8 GB GPU or Mac. CPUs are slow at fp16, so keep fp32 there.
    return torch.float16 if device.type in ("cuda", "mps") else torch.float32


def load_backbone(profile: ModelProfile, device: torch.device) -> nn.Module:
    from transformers import AutoModel

    model = AutoModel.from_pretrained(profile.hf_repo, dtype=backbone_dtype(device))
    return model.to(device).eval()


def fit_input(x: torch.Tensor, crop_px: int = 0) -> torch.Tensor:
    """Optionally centre-crop to `crop_px`, then resize to the backbone's TILE input size.

    Used both at inference (crop a 224px tile to a training patch's field of view) and in
    training (bring e.g. 150px patches up to 224), so both see identical interpolation."""
    if crop_px and crop_px < x.shape[-1]:
        o = (x.shape[-1] - crop_px) // 2
        x = x[..., o : o + crop_px, o : o + crop_px]
    if x.shape[-1] != config.TILE or x.shape[-2] != config.TILE:
        x = F.interpolate(x.float(), size=(config.TILE, config.TILE), mode="bilinear", antialias=True)
    return x


class FoundationEmbedder(nn.Module):
    """[0, 1] NCHW tiles -> tile embeddings (CLS token concatenated with mean patch token)."""

    def __init__(self, backbone: nn.Module, profile: ModelProfile, crop_px: int = 0):
        super().__init__()
        self.backbone = backbone
        self.crop_px = crop_px
        self.register_buffer("mean", torch.tensor(profile.mean).view(1, 3, 1, 1))
        self.register_buffer("std", torch.tensor(profile.std).view(1, 3, 1, 1))

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = (fit_input(x.float(), self.crop_px) - self.mean) / self.std
        dtype = next(self.backbone.parameters()).dtype
        tokens = self.backbone(pixel_values=x.to(dtype)).last_hidden_state.float()
        return torch.cat([tokens[:, 0], tokens[:, 1:].mean(dim=1)], dim=-1)


class FoundationClassifier(nn.Module):
    def __init__(self, embedder: FoundationEmbedder, head: nn.Linear):
        super().__init__()
        self.embedder = embedder
        self.head = head

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # Run the head in fp32 even under the engine's CUDA autocast.
        with torch.autocast(x.device.type, enabled=False):
            return torch.softmax(self.head(self.embedder(x).float()), dim=-1)


def load_head(profile: ModelProfile) -> nn.Linear:
    ckpt = torch.load(profile.head_path, map_location="cpu", weights_only=True)
    if list(ckpt["classes"]) != list(profile.spec.classes):
        raise ValueError(f"{profile.head_path.name} was trained for classes {ckpt['classes']}")
    weight = ckpt["weight"]
    head = nn.Linear(weight.shape[1], weight.shape[0])
    head.load_state_dict({"weight": weight, "bias": ckpt["bias"]})
    return head


def build_classifier(profile: ModelProfile, device: torch.device) -> nn.Module:
    embedder = FoundationEmbedder(load_backbone(profile, device), profile, crop_px=profile.crop_px)
    return FoundationClassifier(embedder, load_head(profile)).to(device).eval()
