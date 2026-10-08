import json
import shutil
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from PIL import Image, UnidentifiedImageError
from sqlalchemy import case as sa_case
from sqlmodel import Session, select

from app import config
from app.db import get_session
from app.inference.stitch import field_paths
from app.models import Case, CaseReview, utcnow
from app.worker import case_dir, run_analysis

router = APIRouter(prefix="/api/cases", tags=["cases"])

ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".webp"}
STATUS_ORDER = {"ready": 0, "analyzing": 1, "queued": 2, "retake": 3, "failed": 4, "reviewed": 5}


def serialize(c: Case) -> dict:
    data = c.model_dump()
    base = f"/media/{c.id}"
    data["original_url"] = f"{base}/{c.filename}"
    d = config.MEDIA_DIR / str(c.id)
    data["field_urls"] = [f"{base}/{p.name}" for p in field_paths(d)]
    quality = d / "quality.json"
    data["quality"] = json.loads(quality.read_text()) if quality.exists() else None
    if c.result:
        data["image_url"] = f"{base}/display.jpg"
        data["heatmap_url"] = f"{base}/heatmap.png"
        if (config.MEDIA_DIR / str(c.id) / "nuclei.json").exists():
            data["nuclei_url"] = f"{base}/nuclei.json"
    return data


def summarize(c: Case) -> dict:
    data = serialize(c)
    result = data.pop("result") or {}
    data["regions_count"] = len(result.get("regions", []))
    data["tumor_fraction"] = result.get("tumor_fraction")
    return data


@router.get("")
def list_cases(status: str | None = None, session: Session = Depends(get_session)):
    """Triage queue: analysed cases first, highest urgency first, oldest first on ties."""
    q = select(Case)
    if status == "active":
        q = q.where(Case.status != "reviewed")
    elif status:
        q = q.where(Case.status == status)
    q = q.order_by(
        sa_case(STATUS_ORDER, value=Case.status, else_=9),
        Case.urgency.desc().nulls_last(),
        Case.created_at.asc(),
    )
    return [summarize(c) for c in session.exec(q).all()]


def _check_image(image: UploadFile) -> str:
    ext = Path(image.filename or "").suffix.lower()
    if ext not in ALLOWED_EXT:
        raise HTTPException(415, f"Unsupported file type '{ext}'. Upload a JPEG, PNG or TIFF photo.")
    if image.size and image.size > config.MAX_UPLOAD_BYTES:
        raise HTTPException(413, f"{image.filename} is larger than 40 MB.")
    try:
        with Image.open(image.file) as im:
            im.verify()
    except (UnidentifiedImageError, OSError):
        raise HTTPException(422, f"{image.filename or 'File'} is not a readable image.")
    image.file.seek(0)
    return ext


@router.post("", status_code=201)
def create_case(
    background: BackgroundTasks,
    image: UploadFile | None = File(None),
    images: list[UploadFile] = File(default=[]),
    patient_ref: str = Form(...),
    clinic: str = Form(""),
    specimen: str = Form(""),
    session: Session = Depends(get_session),
):
    """One photo (`image`), or several overlapping photos of the same slide (`images`),
    which are stitched into a mosaic before analysis."""
    uploads = ([image] if image else []) + images
    if not uploads:
        raise HTTPException(422, "Attach at least one slide photo.")
    if len(uploads) > config.MAX_FIELDS:
        raise HTTPException(413, f"At most {config.MAX_FIELDS} photos per case.")
    exts = [_check_image(u) for u in uploads]

    names = [f"original{exts[0]}"] if len(uploads) == 1 else [f"field_{i:02d}{e}" for i, e in enumerate(exts)]
    c = Case(patient_ref=patient_ref.strip(), clinic=clinic.strip(), specimen=specimen.strip(), filename=names[0])
    session.add(c)
    session.commit()
    session.refresh(c)
    for upload, name in zip(uploads, names):
        with open(case_dir(c.id) / name, "wb") as f:
            shutil.copyfileobj(upload.file, f)
    background.add_task(run_analysis, c.id)
    return serialize(c)


@router.get("/{case_id}")
def get_case(case_id: int, session: Session = Depends(get_session)):
    c = session.get(Case, case_id)
    if c is None:
        raise HTTPException(404, "Case not found")
    return serialize(c)


@router.patch("/{case_id}")
def review_case(case_id: int, review: CaseReview, session: Session = Depends(get_session)):
    c = session.get(Case, case_id)
    if c is None:
        raise HTTPException(404, "Case not found")
    if review.diagnosis is not None:
        c.diagnosis = review.diagnosis
    if review.notes is not None:
        c.notes = review.notes
    if review.status is not None:
        if review.status not in ("reviewed", "ready"):
            raise HTTPException(422, "status must be 'reviewed' or 'ready'")
        c.status = review.status
        c.reviewed_at = utcnow() if review.status == "reviewed" else None
    session.add(c)
    session.commit()
    session.refresh(c)
    return serialize(c)


@router.post("/{case_id}/reanalyze", status_code=202)
def reanalyze(
    case_id: int, background: BackgroundTasks, force: bool = False, session: Session = Depends(get_session)
):
    """Re-run analysis with the active model. `force=true` overrides a quality-gate rejection."""
    c = session.get(Case, case_id)
    if c is None:
        raise HTTPException(404, "Case not found")
    c.status = "queued"
    session.add(c)
    session.commit()
    background.add_task(run_analysis, c.id, force)
    return serialize(c)
