"""Loads the TIAToolbox Kather100k tissue classifier once per process."""

import logging
from functools import lru_cache

import torch
from torch import nn

from app import config
from app.inference.device import pick_device

log = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def load_model() -> tuple[nn.Module, torch.device]:
    from tiatoolbox.models.architecture import get_pretrained_model

    model, _ = get_pretrained_model(config.MODEL_NAME)
    device = pick_device()
    model = model.to(device).eval()
    log.info("Loaded %s on %s", config.MODEL_NAME, device)
    return model, device
