# PathTriage: low-cost edge telepathology

Rural clinics photograph tissue slides through the microscope eyepiece with a smartphone
adapter instead of a $100k slide scanner. A tissue classifier on the clinic's own consumer GPU
analyzes each photo offline and computes a 0–100 urgency score plus a tumor heatmap. A shared
queue then puts the highest-risk patients in front of remote pathologists first.

```
[phone + eyepiece photo] ──► FastAPI + PyTorch/TIAToolbox (RTX 4060 · Apple MPS · CPU) ──► React + Leaflet dashboard
```

> **Triage aid, not a diagnostic device.** The score orders the review queue. Every case is
> still read and signed out by a pathologist.

## How the analysis works

1. **Normalize the photo**: apply EXIF rotation, convert to RGB, and cap the longest side at 2048 px (`TELEPATH_MAX_SIDE`).
2. **Tile**: cut 224 px tiles at a 112 px stride (50% overlap).
3. **Classify**: TIAToolbox's pretrained `resnet18-kather100k` assigns each tile to one of 9 colorectal tissue
   classes (tumor, necrosis, stroma, muscle, lymphocytes, mucosa, mucus, adipose, background).
   Batches run on CUDA (fp16), Apple MPS, or CPU, picked automatically.
4. **Build a probability grid**: overlapping tile predictions are averaged into 112 px cells. Background,
   fat, and the dark eyepiece vignette are masked out as non-tissue.
5. **Find regions**: connected areas where P(tumor)+P(necrosis) ≥ 0.5 and that contain tumor. Each
   region is reported as a bounding box in image pixels with its peak and mean probability, plus a
   hotspot: the centre of its most tumor-like area.
6. **Score urgency**:
   `100 × (0.5·lesion burden + 0.3·peak tumor confidence + 0.2·largest region)`, plus up to
   +10 for tumor-associated necrosis. Tiers: **Critical ≥ 70**, **High ≥ 40**, **Routine** otherwise.
   Weights and thresholds live in [`backend/app/config.py`](backend/app/config.py).
7. **Guide the viewer**: the clearest example of each other tissue type (normal mucosa, necrosis,
   lymphocytes, …) is saved as a landmark, and a colour-coded tissue-type map is rendered. The case
   page's "What to look at" tour visits each hotspot and landmark and lists the visual clues to check,
   so non-specialists can follow a demo.

The model expects tissue at about 0.5 µm/px, which is roughly a 20× objective. Photograph at that
magnification for best results.

## Run it

Requirements: [uv](https://docs.astral.sh/uv/) and Node 20+.

```bash
# Backend (first run downloads PyTorch and the model weights)
cd backend
uv sync
uv run uvicorn app.main:app --port 8000

# Demo data: builds 6 eyepiece-style photos from real Kather CRC-VAL-HE-7K patches
# and uploads them. Patches are range-requested from Zenodo; the first run takes a few minutes.
uv run python scripts/fetch_samples.py --seed

# Dashboard (new terminal), then open http://localhost:5173
cd frontend
npm install
npm run dev
```

**Clinic PC with an RTX 4060 (Windows/Linux):** run the same commands. On non-macOS systems
`pyproject.toml` pulls CUDA 12.6 PyTorch wheels. The dashboard header shows which engine is
active, e.g. `Edge engine · CUDA · NVIDIA GeForce RTX 4060`.

To serve other machines on the clinic LAN, run `uvicorn ... --host 0.0.0.0` and
`npm run dev -- --host`, or build the dashboard (`npm run build`) and serve `frontend/dist`.

## API

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/api/cases` | Multipart `image`, `patient_ref`, `clinic?`, `specimen?`. Creates a case and queues analysis |
| `GET` | `/api/cases?status=active\|reviewed\|<status>` | Triage queue: analyzed first, then urgency ↓, then oldest first |
| `GET` | `/api/cases/{id}` | Case with full result (score, regions, composition, image/heatmap URLs) |
| `PATCH` | `/api/cases/{id}` | Specialist review: `diagnosis`, `notes`, `status` (`reviewed` / `ready`) |
| `POST` | `/api/cases/{id}/reanalyze` | Re-run analysis |
| `GET` | `/api/health` | Device, model status |

Case files are stored under `backend/data/media/<id>/` (original, display JPEG, tumor heatmap PNG, tissue-type map PNG),
with metadata in SQLite at `backend/data/telepath.db`.

## Tests

```bash
cd backend && uv run pytest     # engine geometry, scoring, upload → analysis → queue → review
cd frontend && npm run build    # type-check + production bundle
```

## Layout

```
backend/app/inference/   device selection, model loading, tiling engine, scoring
backend/app/api/         REST endpoints
backend/app/worker.py    background analysis (one job at a time on the GPU)
backend/scripts/         Kather sample builder / seeder
frontend/src/pages/      QueueView (triage queue + upload), CaseView (viewer + review)
frontend/src/components/ SlideViewer (Leaflet CRS.Simple + heatmap overlay), UploadPanel, badges
```
