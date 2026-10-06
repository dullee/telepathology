"""Runs analysis outside the request cycle. One job at a time: a single consumer GPU."""

import logging
import threading

from sqlmodel import Session

from app import config
from app.db import engine
from app.inference.engine import analyze
from app.inference.model import load_model
from app.models import Case, utcnow

log = logging.getLogger(__name__)
_gpu_lock = threading.Lock()


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
            with _gpu_lock:
                model, device = load_model()
                result = analyze(
                    d / case.filename, d / "display.jpg", d / "heatmap.png", model, device,
                    tissue_map_path=d / "tissue.png",
                )
            case.result = result.to_dict()
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
