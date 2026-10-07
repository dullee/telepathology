import logging
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app import config
from app.api.cases import router as cases_router
from app.api.models import router as models_router
from app.db import init_db
from app.inference import model as model_mgr
from app.inference.device import describe, pick_device

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    # Download/load weights in the background so the API is reachable immediately.
    threading.Thread(target=model_mgr.warm, daemon=True).start()
    yield


app = FastAPI(title="Edge Telepathology Triage", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.include_router(cases_router)
app.include_router(models_router)
app.mount("/media", StaticFiles(directory=config.MEDIA_DIR), name="media")


@app.get("/api/health")
def health():
    active = model_mgr.active_profile()
    return {
        "status": "ok",
        "device": describe(pick_device()),
        "model": active.id,
        "model_label": active.label,
        "model_ready": model_mgr.loaded_id() == active.id,
        "model_error": model_mgr.state["error"],
        "classes": config.CLASS_LABELS,
    }
