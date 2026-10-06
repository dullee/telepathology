import torch


def pick_device() -> torch.device:
    """Prefer an NVIDIA GPU (e.g. the clinic RTX 4060), then Apple Silicon, then CPU."""
    if torch.cuda.is_available():
        return torch.device("cuda")
    if torch.backends.mps.is_available():
        return torch.device("mps")
    return torch.device("cpu")


def describe(device: torch.device) -> str:
    if device.type == "cuda":
        return f"CUDA · {torch.cuda.get_device_name(device)}"
    if device.type == "mps":
        return "Apple MPS"
    return "CPU"
