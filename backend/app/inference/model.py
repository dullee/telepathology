"""Holds the active tile classifier. One model at a time: a consumer GPU has room for one.

The active choice is persisted in DATA_DIR/active_model.json (falls back to TELEPATH_MODEL),
so a switch made from the dashboard survives restarts.
"""

from __future__ import annotations

import gc
import json
import logging
import threading
from contextlib import contextmanager
from dataclasses import dataclass

import torch
from torch import nn

from app import config
from app.inference.device import pick_device
from app.inference.registry import ModelProfile, get_profile

log = logging.getLogger(__name__)


class GpuScheduler:
    """One job on the GPU at a time, with triage first.

    `urgent()` (loading the classifier, scoring a case) always runs before `background()` work
    (cell counting). Background work takes the GPU in short slices, one chunk at a time, and
    waits while any urgent job is queued, so a new case is never stuck behind minutes of
    cell counting. Holding either slot also means a model switch never swaps weights mid-use.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._cv = threading.Condition()
        self._urgent_waiting = 0

    @contextmanager
    def urgent(self):
        with self._cv:
            self._urgent_waiting += 1
        try:
            self._lock.acquire()
        finally:
            with self._cv:
                self._urgent_waiting -= 1
                self._cv.notify_all()
        try:
            yield
        finally:
            self._lock.release()

    @contextmanager
    def background(self):
        with self._cv:
            self._cv.wait_for(lambda: self._urgent_waiting == 0)
        with self._lock:
            yield


GPU = GpuScheduler()
_SETTINGS = config.DATA_DIR / "active_model.json"


@dataclass
class Loaded:
    profile: ModelProfile
    model: nn.Module
    device: torch.device


_loaded: Loaded | None = None
state = {"loading": "", "error": ""}


def _read_active() -> str:
    try:
        saved = json.loads(_SETTINGS.read_text())["model"]
        if get_profile(saved).availability()[0]:
            return saved
    except (OSError, ValueError, KeyError):
        pass
    return config.MODEL_NAME


_active_id = _read_active()


def active_profile() -> ModelProfile:
    return get_profile(_active_id)


def loaded_id() -> str:
    return _loaded.profile.id if _loaded else ""


def set_active(model_id: str) -> ModelProfile:
    """Persist a new active model. It is loaded lazily (see warm / load_model)."""
    global _active_id
    profile = get_profile(model_id)
    ok, reason = profile.availability()
    if not ok:
        raise ValueError(reason)
    _active_id = profile.id
    _SETTINGS.parent.mkdir(parents=True, exist_ok=True)
    _SETTINGS.write_text(json.dumps({"model": profile.id}))
    state["error"] = ""
    return profile


def _build(profile: ModelProfile, device: torch.device) -> nn.Module:
    if profile.family == "foundation":
        from app.inference.foundation import build_classifier

        return build_classifier(profile, device)
    from tiatoolbox.models.architecture import get_pretrained_model

    model, _ = get_pretrained_model(profile.tiatoolbox_name)
    return model.to(device).eval()


def _release() -> None:
    global _loaded
    if _loaded is None:
        return
    _loaded = None
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
    elif torch.backends.mps.is_available():
        torch.mps.empty_cache()


def load_model() -> Loaded:
    """Return the active model, (re)loading it if the selection changed. Call inside GPU.urgent()."""
    global _loaded
    profile = active_profile()
    if _loaded and _loaded.profile.id == profile.id:
        return _loaded
    _release()
    state["loading"] = profile.id
    try:
        device = pick_device()
        _loaded = Loaded(profile, _build(profile, device), device)
        state["error"] = ""
        log.info("Loaded %s on %s", profile.id, device)
        return _loaded
    except Exception as exc:
        state["error"] = f"{profile.label}: {exc}"
        raise
    finally:
        state["loading"] = ""


def warm() -> None:
    """Load the active model in the background so the first case doesn't pay for it."""
    try:
        with GPU.urgent():
            load_model()
    except Exception:
        log.exception("Model failed to load")
