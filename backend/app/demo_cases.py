"""Start a new installation with the dashboard's demo cases, so the queue isn't empty.

The cases are the snapshot the hosted dashboard shows without a backend (frontend/public/demo/,
written by scripts/export_demo.py), so starting the backend keeps the same cases on screen. The
snapshot leaves out full-size originals, which Re-analyze needs; they come from backend/samples/.
Runs only while the database has no cases. TELEPATH_DEMO_CASES=0 turns it off.
"""

import json
import logging
import shutil
from datetime import timedelta

from sqlmodel import Session, select

from app import config
from app.db import engine
from app.models import Case, utcnow

log = logging.getLogger(__name__)

SNAPSHOT = config.BASE_DIR.parent / "frontend" / "public" / "demo"
SAMPLES = config.BASE_DIR / "samples"
# Patient ref -> sample the case was uploaded from (see scripts/fetch_samples.py).
SOURCES = {
    "KE-0412": "advanced_adenocarcinoma.jpg",
    "KE-0398": "invasive_focus.jpg",
    "UG-1187": "small_suspicious_focus.jpg",
    "TZ-0033": "inflamed_mucosa.jpg",
    "KE-0420": "normal_mucosa.jpg",
    "UG-1201": "mucinous_lesion.jpg",
    "KE-0431": "mosaic_large_tumor",
    "UG-1215": "mosaic_benign_mucosa",
    "TZ-0051": "mosaic_one_blurry_photo",
}
CASE_FIELDS = ("id", "patient_ref", "clinic", "specimen", "filename", "status", "urgency", "tier",
               "diagnosis", "notes", "error", "result")


def _copy_media(c: dict) -> None:
    src, dst = SNAPSHOT / "media" / str(c["id"]), config.MEDIA_DIR / str(c["id"])
    shutil.copytree(src, dst, dirs_exist_ok=True)
    if c["patient_ref"] not in SOURCES:
        return  # the snapshot already has its original (a case without a result)
    source = SAMPLES / SOURCES[c["patient_ref"]]
    if source.is_file():
        shutil.copy2(source, dst / c["filename"])
    elif source.is_dir():
        # The snapshot's field photos are thumbnails; use the full-size photos.
        for i, photo in enumerate(sorted(source.glob("*.jpg"))):
            shutil.copy2(photo, dst / f"field_{i:02d}.jpg")


def seed_demo_cases() -> None:
    if not config.DEMO_CASES or not (SNAPSHOT / "data.json").exists():
        return
    with Session(engine) as session:
        if session.exec(select(Case.id).limit(1)).first() is not None:
            return
        cases = json.loads((SNAPSHOT / "data.json").read_text())["cases"]
        # Show them as recent uploads, a few minutes apart, newest first (as the hosted demo does).
        now = utcnow()
        for i, c in enumerate(sorted(cases, key=lambda c: c["created_at"], reverse=True)):
            created = now - timedelta(minutes=4 + i * 11)
            _copy_media(c)
            session.add(Case(
                **{k: c[k] for k in CASE_FIELDS},
                created_at=created,
                analyzed_at=created + timedelta(seconds=40) if c["analyzed_at"] else None,
            ))
        session.commit()
    log.info("Added %d demo cases to the empty queue", len(cases))
