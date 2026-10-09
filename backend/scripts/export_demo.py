"""Snapshot analysed cases from the running backend into the dashboard's built-in demo.

The hosted dashboard (Vercel) falls back to this snapshot when it can't reach a backend, so the
triage queue can be shown on any computer. Writes frontend/public/demo/: data.json (health, models,
cases) and each case's images, with /media/ URLs rewritten to /demo/media/.

    uv run python scripts/export_demo.py                  # default demo cases
    uv run python scripts/export_demo.py --ids 1 2 18     # pick cases
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

import httpx
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
MEDIA = ROOT / "data" / "media"
OUT = ROOT.parent / "frontend" / "public" / "demo"
# The six single colon photos, the three stitched colon cases, and one photo the quality gate rejects.
DEFAULT_IDS = [1, 2, 3, 4, 5, 6, 16, 18, 19, 20]
# Case labels to replace, for cases uploaded during testing.
RELABEL = {16: {"patient_ref": "KE-0447", "clinic": "Busia Sub-County Clinic", "specimen": "Lung biopsy"}}
# Stitched cases' source photos are only shown as thumbnails; shrink them to keep the deploy small.
FIELD_MAX_SIDE = 1024


def rewrite(value):
    if isinstance(value, str) and value.startswith("/media/"):
        return "/demo" + value
    if isinstance(value, list):
        return [rewrite(v) for v in value]
    if isinstance(value, dict):
        return {k: rewrite(v) for k, v in value.items()}
    return value


def copy_media(case: dict) -> None:
    """Copy the files the dashboard shows. The original photo is only shown before a result exists,
    and a stitched case's mosaic.jpg not at all."""
    src, dst = MEDIA / str(case["id"]), OUT / "media" / str(case["id"])
    dst.mkdir(parents=True)
    for f in src.iterdir():
        if f.name == "mosaic.jpg" or (case["result"] and f.name.startswith("original.")):
            continue
        if f.name.startswith("field_"):
            img = Image.open(f)
            img.thumbnail((FIELD_MAX_SIDE, FIELD_MAX_SIDE))
            img.convert("RGB").save(dst / f.name, quality=82)
        else:
            shutil.copy2(f, dst / f.name)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--api", default="http://localhost:8000")
    ap.add_argument("--ids", type=int, nargs="+", default=DEFAULT_IDS)
    args = ap.parse_args()

    with httpx.Client(base_url=args.api, timeout=30) as api:
        cases = [{**api.get(f"/api/cases/{i}").raise_for_status().json(), **RELABEL.get(i, {})} for i in args.ids]
        busy = [c["id"] for c in cases if c["status"] in ("queued", "analyzing")
                or ((c.get("result") or {}).get("cells") or {}).get("status") == "counting"]
        if busy:
            raise SystemExit(f"Cases {busy} are still being analysed; wait and run again.")
        data = {
            "health": api.get("/api/health").raise_for_status().json(),
            "models": api.get("/api/models").raise_for_status().json(),
            "cases": cases,
        }

    shutil.rmtree(OUT, ignore_errors=True)
    OUT.mkdir(parents=True)
    for c in cases:
        copy_media(c)
    (OUT / "data.json").write_text(json.dumps(rewrite(data), separators=(",", ":")))
    size = sum(f.stat().st_size for f in OUT.rglob("*") if f.is_file())
    print(f"Wrote {len(cases)} cases to {OUT} ({size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
