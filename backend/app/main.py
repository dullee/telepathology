import logging
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app import config
from app.api.cases import router as cases_router
from app.db import init_db
from app.inference.device import describe, pick_device
from app.inference.model import load_model

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
state = {"model_ready": False, "model_error": ""}


def _warm_model() -> None:
    try:
        load_model()
        state["model_ready"] = True
    except Exception as exc:
        state["model_error"] = str(exc)
        logging.exception("Model failed to load")


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    # Download/load weights in the background so the API is reachable immediately.
    threading.Thread(target=_warm_model, daemon=True).start()
    yield


app = FastAPI(title="Edge Telepathology Triage", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.include_router(cases_router)
app.mount("/media", StaticFiles(directory=config.MEDIA_DIR), name="media")


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "device": describe(pick_device()),
        "model": config.MODEL_NAME,
        "model_ready": state["model_ready"],
        "model_error": state["model_error"],
        "classes": config.CLASS_LABELS,
    }
