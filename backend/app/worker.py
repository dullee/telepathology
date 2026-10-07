"""Runs analysis outside the request cycle. One job at a time: a single consumer GPU."""

import logging

from sqlmodel import Session

from app import config
from app.db import engine
from app.inference.engine import analyze
from app.inference.model import GPU_LOCK, load_model
from app.models import Case, utcnow

log = logging.getLogger(__name__)


def case_dir(case_id: int):
    d = config.MEDIA_DIR / str(case_id)
    d.mkdir(parents=True, exist_ok=True)
    return d


def run_analysis(case_id: int) -> None:
    with Session(engine) as session:
        case = session.get(Case, case_id)
        if case is None:
            return
        case.status = "analyzing"
        session.add(case)
        session.commit()

        d = case_dir(case_id)
        try:
            with GPU_LOCK:
                loaded = load_model()
                p = loaded.profile
                result = analyze(
                    d / case.filename, d / "display.jpg", d / "heatmap.png", loaded.model, loaded.device, p.spec
                )
            case.result = {
                **result.to_dict(),
                "model": p.id,
                "model_label": p.label,
                "organ": p.organ,
                "class_labels": p.spec.labels,
                "tumor_classes": list(p.spec.tumor),
            }
            case.urgency = result.urgency
            case.tier = result.tier
            case.status = "ready"
            case.error = ""
        except Exception as exc:  # surfaced to the clinic in the UI
            log.exception("Analysis failed for case %s", case_id)
            case.status = "failed"
            case.error = str(exc)[:500]
        case.analyzed_at = utcnow()
        session.add(case)
        session.commit()
