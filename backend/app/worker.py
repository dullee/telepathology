"""Runs analysis outside the request cycle. One job at a time: a single consumer GPU.

0. Quality gate: every photo is checked for focus, exposure, tissue and staining. Unusable
   photos are left out of a stitch; if nothing usable remains the case asks for a retake
   (status "retake") unless analysis is forced. The report is saved as quality.json.
1. Stitch: several photos of one slide become mosaic.jpg (skipped for a single photo).
2. Classify: tissue heatmap, regions and urgency. The case becomes "ready" here, so the
   triage queue never waits for step 3.
3. Count cells: typed nuclei with HoVer-Net, saved to nuclei.json plus a summary in the
   result. Failure here never fails the case.
"""

import json
import logging

from PIL import Image
from sqlmodel import Session

from app import config
from app.db import engine
from app.inference.engine import analyze, prepare_image
from app.inference.model import GPU, load_model
from app.inference.quality import QualityReport, assess
from app.inference.stitch import StitchError, field_paths, stitch
from app.models import Case, utcnow

log = logging.getLogger(__name__)


def case_dir(case_id: int):
    d = config.MEDIA_DIR / str(case_id)
    d.mkdir(parents=True, exist_ok=True)
    return d


def _save(session: Session, case: Case) -> None:
    session.add(case)
    session.commit()
    session.refresh(case)


def _prepare(d, case: Case, force: bool):
    """Quality-check the photo(s) and stitch if needed.
    Returns (report, source image path, max_side for analysis, fields info or None)."""
    paths = field_paths(d)
    if len(paths) <= 1:
        return assess(prepare_image(d / case.filename)), d / case.filename, config.MAX_SIDE, None

    images = [prepare_image(p) for p in paths]
    reports = [assess(im) for im in images]
    keep = [i for i, r in enumerate(reports) if force or r.status != "reject"]
    dropped = [{"photo": i + 1, "reason": reports[i].summary("reject")} for i in range(len(paths)) if i not in keep]
    if not keep:
        worst = reports[0]
        return QualityReport("reject", worst.checks, dropped), d / case.filename, config.MAX_SIDE, None
    if len(keep) == 1:
        report = reports[keep[0]]
        report.dropped = dropped
        report.status = "warn" if report.status == "pass" else report.status
        return report, paths[keep[0]], config.MAX_SIDE, {"uploaded": len(paths), "stitched": 1, "downscale": 1.0}

    mosaic = stitch([images[i] for i in keep])
    mosaic.image.save(d / "mosaic.jpg", "JPEG", quality=92)
    report = assess(mosaic.image)
    report.dropped = dropped
    if dropped and report.status == "pass":
        report.status = "warn"
    fields = {"uploaded": len(paths), "stitched": mosaic.used, "downscale": mosaic.downscale}
    return report, d / "mosaic.jpg", config.MOSAIC_MAX_SIDE, fields


def run_analysis(case_id: int, force: bool = False) -> None:
    """`force` analyses even photos the quality gate would reject (a reviewer's override)."""
    with Session(engine) as session:
        case = session.get(Case, case_id)
        if case is None:
            return
        case.status = "analyzing"
        _save(session, case)

        d = case_dir(case_id)
        (d / "nuclei.json").unlink(missing_ok=True)
        try:
            report, source, max_side, fields = _prepare(d, case, force)
            (d / "quality.json").write_text(json.dumps({**report.to_dict(), "forced": force}))
            if report.status == "reject" and not force:
                case.status = "retake"
                case.error = report.summary()
                case.result, case.urgency, case.tier = None, None, None
                case.analyzed_at = utcnow()
                _save(session, case)
                return
            with GPU.urgent():
                loaded = load_model()
                p = loaded.profile
                result = analyze(
                    source, d / "display.jpg", d / "heatmap.png", loaded.model, loaded.device, p.spec, max_side
                )
            case.result = {
                **result.to_dict(),
                "model": p.id,
                "model_label": p.label,
                "organ": p.organ,
                "class_labels": p.spec.labels,
                "tumor_classes": list(p.spec.tumor),
                "fields": fields,
                "cells": {"status": "counting"} if config.CELL_COUNTING else None,
            }
            case.urgency = result.urgency
            case.tier = result.tier
            case.status = "ready"
            case.error = ""
        except StitchError as exc:
            case.status = "failed"
            case.error = str(exc)
        except Exception as exc:  # surfaced to the clinic in the UI
            log.exception("Analysis failed for case %s", case_id)
            case.status = "failed"
            case.error = str(exc)[:500]
        case.analyzed_at = utcnow()
        _save(session, case)

        if case.status == "ready" and config.CELL_COUNTING:
            _count_cells(session, case, d, loaded.device)


def resume_interrupted() -> None:
    """Re-run cases a restart interrupted (power cut, crash, update): they would otherwise sit
    in "queued"/"analyzing" forever. Unfinished cell counts are redone the same way."""
    from sqlmodel import select

    with Session(engine) as session:
        stuck = session.exec(select(Case).where(Case.status.in_(["queued", "analyzing"]))).all()
        recount = [
            c for c in session.exec(select(Case).where(Case.status == "ready")).all()
            if (c.result or {}).get("cells", {}) and c.result["cells"].get("status") == "counting"
        ]
        ids = [c.id for c in stuck] + [c.id for c in recount]
    if ids:
        log.info("Resuming %d interrupted case(s): %s", len(ids), ids)
    for case_id in ids:
        run_analysis(case_id)


def _count_cells(session: Session, case: Case, d, device) -> None:
    from app.inference.cells import count_cells

    try:
        # Takes the GPU chunk by chunk via GPU.background(), yielding to newly uploaded cases.
        cells = count_cells(Image.open(d / "display.jpg"), device, case.result["tissue_fraction"], gpu=GPU.background)
        (d / "nuclei.json").write_text(json.dumps({"points": cells.points}, separators=(",", ":")))
        summary = {"status": "done", **cells.summary()}
    except Exception as exc:
        log.exception("Cell counting failed for case %s", case.id)
        summary = {"status": "failed", "error": str(exc)[:300]}
    # Reassign (not mutate) so SQLAlchemy sees the JSON column change.
    case.result = {**case.result, "cells": summary}
    _save(session, case)
