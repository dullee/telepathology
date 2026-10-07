import threading

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.inference import model as model_mgr
from app.inference.registry import PROFILES

router = APIRouter(prefix="/api/models", tags=["models"])


class ModelChoice(BaseModel):
    id: str


def model_status() -> dict:
    active = model_mgr.active_profile()
    profiles = dict(PROFILES)
    profiles.setdefault(active.id, active)  # an uncurated TELEPATH_MODEL choice
    return {
        "active": active.id,
        "loaded": model_mgr.loaded_id(),
        "loading": model_mgr.state["loading"],
        "error": model_mgr.state["error"],
        "models": [p.to_dict() for p in profiles.values()],
    }


@router.get("")
def list_models():
    return model_status()


@router.put("/active")
def choose_model(choice: ModelChoice):
    """Switch the classifier used for new uploads and re-analyses. Loads in the background."""
    try:
        model_mgr.set_active(choice.id)
    except KeyError as exc:
        raise HTTPException(404, str(exc.args[0]))
    except ValueError as exc:
        raise HTTPException(409, str(exc))
    if model_mgr.loaded_id() != choice.id:
        threading.Thread(target=model_mgr.warm, daemon=True).start()
    return model_status()
