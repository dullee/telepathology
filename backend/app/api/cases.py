import shutil
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from PIL import Image, UnidentifiedImageError
from sqlalchemy import case as sa_case
from sqlmodel import Session, select

from app import config
from app.db import get_session
from app.models import Case, CaseReview, utcnow
from app.worker import case_dir, run_analysis

router = APIRouter(prefix="/api/cases", tags=["cases"])

ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".webp"}
STATUS_ORDER = {"ready": 0, "analyzing": 1, "queued": 2, "failed": 3, "reviewed": 4}


def serialize(c: Case) -> dict:
    data = c.model_dump()
    base = f"/media/{c.id}"
    data["original_url"] = f"{base}/{c.filename}"
    if c.result:
        data["image_url"] = f"{base}/display.jpg"
        data["heatmap_url"] = f"{base}/heatmap.png"
        # Cases analysed before the tissue map existed don't have one until re-analysed.
        if (config.MEDIA_DIR / str(c.id) / "tissue.png").exists():
            data["tissue_map_url"] = f"{base}/tissue.png"
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


@router.post("", status_code=201)
def create_case(
    background: BackgroundTasks,
    image: UploadFile = File(...),
    patient_ref: str = Form(...),
    clinic: str = Form(""),
    specimen: str = Form(""),
    session: Session = Depends(get_session),
):
    ext = Path(image.filename or "").suffix.lower()
    if ext not in ALLOWED_EXT:
        raise HTTPException(415, f"Unsupported file type '{ext}'. Upload a JPEG, PNG or TIFF photo.")
    if image.size and image.size > config.MAX_UPLOAD_BYTES:
        raise HTTPException(413, "Image is larger than 40 MB.")
    try:
        with Image.open(image.file) as im:
            im.verify()
    except (UnidentifiedImageError, OSError):
        raise HTTPException(422, "File is not a readable image.")
    image.file.seek(0)

    c = Case(patient_ref=patient_ref.strip(), clinic=clinic.strip(), specimen=specimen.strip(),
             filename=f"original{ext}")
    session.add(c)
    session.commit()
    session.refresh(c)
    with open(case_dir(c.id) / c.filename, "wb") as f:
        shutil.copyfileobj(image.file, f)
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
def reanalyze(case_id: int, background: BackgroundTasks, session: Session = Depends(get_session)):
    c = session.get(Case, case_id)
    if c is None:
        raise HTTPException(404, "Case not found")
    c.status = "queued"
    session.add(c)
    session.commit()
    background.add_task(run_analysis, c.id)
    return serialize(c)
