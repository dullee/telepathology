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

1. **Check photo quality**: before any model runs, each photo is graded for focus, exposure, tissue in
   view, H&E staining and resolution (see [Photo quality gate](#photo-quality-gate)). Unusable photos ask the
   clinic for a retake.
2. **Stitch (several photos)**: overlapping photos of one slide are aligned and blended into a single mosaic
   (see [Stitching](#stitching-several-photos)). A single photo skips this step.
3. **Normalize the photo**: apply EXIF rotation, convert to RGB, and cap the longest side at 2048 px (`TELEPATH_MAX_SIDE`).
4. **Tile**: cut 224 px tiles at a 112 px stride (50% overlap).
5. **Classify**: the active model (default: TIAToolbox's `resnet18-kather100k`; see [Models](#models))
   assigns each tile to one of 9 colorectal tissue classes (tumor, necrosis, stroma, muscle, lymphocytes,
   mucosa, mucus, adipose, background).
   Batches run on CUDA (fp16), Apple MPS, or CPU, picked automatically.
6. **Build a probability grid**: overlapping tile predictions are averaged into 112 px cells. Background,
   fat, and the dark eyepiece vignette are masked out as non-tissue.
7. **Find regions**: connected areas where P(tumor)+P(necrosis) ≥ 0.5 and that contain tumor. Each
   region is reported as a bounding box in image pixels with its peak and mean probability, plus a
   hotspot: the centre of its most tumor-like area.
8. **Score urgency**:
   `100 × (0.5·lesion burden + 0.3·peak tumor confidence + 0.2·largest region)`, plus up to
   +10 for tumor-associated necrosis. Tiers: **Critical ≥ 70**, **High ≥ 40**, **Routine** otherwise.
   Weights and thresholds live in [`backend/app/config.py`](backend/app/config.py).
9. **Guide the viewer**: the clearest example of each other tissue type the active model knows (normal
   mucosa, necrosis, lymphocytes, … or, for liver, fibrosis, steatosis, …) is saved as a landmark, and a
   colour-coded tissue-type map is rendered. The case page's "What to look at" tour visits each hotspot and landmark and lists the visual clues to check,
   so non-specialists can follow a demo.
10. **Count cells** (after the case is already in the queue): HoVer-Net finds and types every nucleus
   (see [Cell counting](#cell-counting)).

The model expects tissue at about 0.5 µm/px, which is roughly a 20× objective. Photograph at that
magnification for best results.

### Photo quality gate

[`quality.py`](backend/app/inference/quality.py) grades each photo before analysis.

| Check | Warn | Reject (retake) |
| --- | --- | --- |
| Focus (median over tissue tiles of var(Laplacian) / var(gray)) | < 1.5 (cell types unreliable) | < 0.4 (about 1.5–2 px of blur) |
| Brightness of the lit field | < 90 | < 55 |
| Overexposed (clipped) share | > 35% | > 70% |
| Tissue in view | < 15% | < 3% |
| H&E colouring of tissue pixels | < 50% | < 20% |
| Longest side | < 1000 px | < 224 px |

The focus thresholds were calibrated on LungHist700 microscope-camera photos with added blur: sharp photos
score about 3.2, a 0.8 px blur about 1.3, and a 1.6 px blur about 0.3.

- **Reject:** the case becomes **Retake photo** and isn't analysed. The case page explains what to fix,
  and a reviewer can still choose **Analyse anyway**.
- **Warn:** the case is analysed and the warnings are shown above the score.
- **Several photos:** each is checked before stitching. Rejected ones are left out and listed with the
  reason. The report is saved per case as `quality.json`.

### Stitching several photos

Drop several photos into the upload panel; on a phone, they can be added one at a time. Move the stage
about two-thirds of a field between shots so each photo overlaps its neighbours by about a third, and keep
the same objective and focus. [`stitch.py`](backend/app/inference/stitch.py) works as follows:

- It masks the dark eyepiece ring in each photo.
- It matches SIFT features between every pair of photos and fits shift + rotation + scale with RANSAC.
- It chains the photos along the strongest matches and blends them, with weights that fade to zero at each
  field's edge, so the ring and seams don't show.

Photos that don't overlap anything are left out, and the case page reports this ("Stitched from 5 of 6
photos"). If nothing lines up, the case fails with capture guidance. The mosaic is analysed at full
resolution, up to 12,000 px (`TELEPATH_MOSAIC_MAX_SIDE`), with at most 40 photos per case. The result is a
stitched panorama at one magnification, not a multi-resolution scanner WSI.

### Cell counting

[`cells.py`](backend/app/inference/cells.py) runs TIAToolbox's `hovernet_fast-pannuke` and reports:
- nuclei counted and typed as neoplastic, inflammatory, connective, dead or benign epithelial
- % neoplastic
- nuclei per mm² of tissue
- an overlay of every nucleus in the viewer (Cells toggle)

It runs as a second stage, so the urgency score is never delayed. Set `TELEPATH_CELLS=0` to turn it off.
The GPU is shared triage-first: cell counting takes it one chunk at a time and steps aside whenever a newly
uploaded case is waiting to be scored. Cases interrupted by a restart or power cut are resumed when the
backend starts again.

- **Scale:** HoVer-Net was trained at 0.25 µm/px (40×), so photos are upscaled 2× from the assumed
  0.5 µm/px. Set `TELEPATH_UM_PER_PX` if your phone and objective setup differs. Counts and densities depend
  on this.
- **Speed:** on an 8 GB Apple M3 it runs at batch 1 (3.5 patches/s), about 2 minutes per photo. A CUDA GPU
  uses batches of 16 (`TELEPATH_CELL_BATCH`).
- **Blur:** detection holds up well on blurry photos, but **typing does not**. On a lung adenocarcinoma photo,
  a 0.8 px blur cut detected nuclei by only 8% (1,641 → 1,510), but dropped "neoplastic" from 50% to 13%:
  blurred tumor nuclei read as connective or benign. Use sharp, in-focus photos, and treat type fractions
  as indicative only.
- **License:** the PanNuke training data is CC BY-NC-SA 4.0, so cell counting is for non-commercial and
  research use.

## Run it

### First-time setup on a new computer

The backend needs [uv](https://docs.astral.sh/uv/), which also installs the right Python (3.11 or
3.12) by itself. The dashboard needs Node 20+, but only if you run it locally instead of using the
hosted dashboard (see below). Install them once:

1. **Git**: macOS: run `xcode-select --install`. Windows: install [Git for Windows](https://git-scm.com/download/win).
   Linux: `sudo apt install git`.
2. **uv**:
   - macOS / Linux: `curl -LsSf https://astral.sh/uv/install.sh | sh`
   - Windows (PowerShell): `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`

   Then close and reopen the terminal, and check that `uv --version` prints a version.
3. **Node 20+** (local dashboard only): install the LTS version from [nodejs.org](https://nodejs.org/).
   Then reopen the terminal, and check that `node --version` prints v20 or newer.
4. **Get the code**: `git clone <repo URL>`, then `cd` into the folder.
5. **Windows/Linux with an NVIDIA GPU**: install a current NVIDIA driver (CUDA 12.6 or newer; check
   with `nvidia-smi`). You don't need the CUDA toolkit, because PyTorch brings its own.

Then follow the steps below. The first `uv sync` downloads PyTorch and the other packages (a few GB,
so expect 5–15 minutes), and the first analysis downloads the model weights.

**Troubleshooting**
- `uv: command not found`: reopen the terminal so it picks up the new PATH, or run
  `source $HOME/.local/bin/env` (macOS/Linux).
- `Failed to spawn: uvicorn` after copying or moving the project folder: the virtual environment
  remembers its old location. In `backend/`, delete it with `rm -rf .venv` (Windows:
  `rmdir /s /q .venv`), then run `uv sync` again. Don't copy `.venv` or `node_modules` between computers.
- `npm: command not found`: Node isn't installed. Install it (step 3), or use the hosted dashboard.

### Start it

```bash
# Backend (first run downloads PyTorch and the model weights)
cd backend
uv sync
uv run uvicorn app.main:app --port 8000

# Demo data: builds 6 eyepiece-style photos plus 3 stitched cases (9, 6 and 6 overlapping photos,
# one of them deliberately out of focus) from real Kather CRC-VAL-HE-7K patches
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

**Hosted dashboard:** https://pathtriage.vercel.app is built with `VITE_API_BASE=http://localhost:8000`,
so it talks to the backend on whichever computer opens it. Start the backend, then open the site
(Chrome, Edge or Firefox; allow local network access if asked). No `npm` step is needed on that
machine. The Vercel project builds `frontend/` (its Root Directory) and redeploys on every push to
`main`; `VITE_API_BASE` is set in the project's environment variables.
`VITE_API_BASE` can instead point at any public backend URL (for example a Tailscale Funnel address).

## Models

Click the engine pill in the dashboard header to switch models. The choice is saved to
`backend/data/active_model.json` and applies to new uploads and re-analyses. Each result records the model
that produced it, and **Re-analyze** on a case runs it again with the current model. `TELEPATH_MODEL` sets
the default before anything is picked. It also accepts any TIAToolbox `*-kather100k` backbone, for example
`densenet161-kather100k`.

| Model | Type | Size | Notes |
| --- | --- | --- | --- |
| `resnet18-kather100k` | CNN | 11M | Default. Fast enough for CPU. |
| `mobilenet_v3_large-kather100k` | CNN | 5M | Lightest option, for clinic PCs without a GPU. |
| `wide_resnet50_2-kather100k` | CNN | 67M | More accurate CNN. |
| `midnight-kather100k` | Foundation | 1.1B | [kaiko-ai/Midnight-12k](https://huggingface.co/kaiko-ai/midnight) (MIT, ungated) + a trained 9-class head. Most robust to stain and phone-camera shift. 4.5 GB download on first use. Use a GPU. |
| `midnight-gastric` | Foundation, **stomach** | 1.1B | Midnight + 8-class gastric head (tumor, normal mucosa, stroma, muscle, lymphocytes, mucus, debris, adipose). |
| `midnight-liver` | Foundation, **liver** | 1.1B | Midnight + 7-class liver head (HCC, normal, fibrosis, inflammation, necrosis, steatosis, bile duct reaction). |
| `midnight-lung` | Foundation, **lung** | 1.1B | Midnight + 3-class lung head (adenocarcinoma, squamous cell carcinoma, normal). Both carcinoma classes count as tumor. |

The picker groups models by organ. Choose the model that matches the specimen: an organ head only knows
its own tissue classes.

**Why Midnight.** Among pathology foundation models it scores at the top of the public eva benchmark
(UNI2 and Virchow2 level, ahead of H-optimus-0 and Prov-GigaPath). Its weights are MIT-licensed and
downloadable without an access request, which matters for deployment. UNI, Virchow and CONCH are
non-commercial (CC-BY-NC-ND). It was pretrained on TCGA slides spanning 32 cancer types, so it is also the best
starting point for heads covering other tissues. It runs in fp16 (about 2.3 GB) on CUDA and MPS.

Foundation models output features, not classes. The head in `backend/app/inference/heads/` is a linear
probe on Midnight embeddings, trained on Kather100k with phone-capture augmentation and validated on the
held-out CRC-VAL-HE-7K patients. To retrain it:

```bash
cd backend && uv run python scripts/train_head.py      # --per-class 500 for a bigger probe
```

Validation on CRC-VAL-HE-7K (100 patches per class, patients not seen in training). "Phone-degraded" adds
blur, colour cast, noise and JPEG compression:

| Model | Clean | Phone-degraded | Tumor recall (degraded) |
| --- | --- | --- | --- |
| `resnet18-kather100k` | 76.8% | 73.7% | 79% |
| `midnight-kather100k` | 92.0% | 94.3% | 98% |

Midnight runs at about 2.7 tiles/s on an Apple M3 (8 GB), so a typical 165-tile photo takes about
2 minutes. Use a CUDA GPU, or set `TELEPATH_STRIDE=224` for about 4× fewer tiles.

Organ heads are trained the same way (`--model midnight-gastric | midnight-liver | midnight-lung`) on these
public datasets (all CC-BY 4.0):

| Head | Dataset | Validation split |
| --- | --- | --- |
| Stomach | [HMU-GC-HE-30K](https://doi.org/10.6084/m9.figshare.25954813): 31k patches, 300 slides | Highest-numbered 20% per class. There are no patient IDs, so this split may leak. |
| Liver | [HepatoBench](https://huggingface.co/datasets/xtxx/HepatoBench): 87k patches at 150 px, 20× | As stomach. Tiles are centre-cropped to 150 px at inference to match. |
| Lung | [LungHist700](https://doi.org/10.6084/m9.figshare.25459174): 691 microscope-camera images, 45 patients | Held-out patients. Labels are per image, so stroma inside a tumor image counts as tumor. |

To add a model, add a `ModelProfile` to [`registry.py`](backend/app/inference/registry.py), with a `ClassSpec`
that lists its output classes and which of them count as tumor, necrosis and non-tissue.

## API

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/api/cases` | Multipart `image` (one photo) or repeated `images` (stitched), plus `patient_ref`, `clinic?`, `specimen?`. Creates a case and queues analysis |
| `GET` | `/api/cases?status=active\|reviewed\|<status>` | Triage queue: analyzed first, then urgency ↓, then oldest first |
| `GET` | `/api/cases/{id}` | Case with full result (score, regions, composition, image/heatmap URLs) |
| `PATCH` | `/api/cases/{id}` | Specialist review: `diagnosis`, `notes`, `status` (`reviewed` / `ready`) |
| `POST` | `/api/cases/{id}/reanalyze?force=` | Re-run analysis with the active model. `force=true` overrides a quality-gate rejection |
| `GET` | `/api/models` | Available models, the active one, load status |
| `PUT` | `/api/models/active` | JSON `{"id": "midnight-kather100k"}`. Switches the model and loads it in the background |
| `GET` | `/api/health` | Device, model status |

Case files are stored under `backend/data/media/<id>/` (original or `field_NN` photos, `mosaic.jpg`, display JPEG,
tumor heatmap PNG, tissue-type map PNG, `nuclei.json`, `quality.json`),
with metadata in SQLite at `backend/data/telepath.db`.

## Tests

```bash
cd backend && uv run pytest     # engine geometry, scoring, upload → analysis → queue → review
cd frontend && npm run build    # type-check + production bundle
```

## Layout

```
backend/app/inference/   model registry + switching, foundation-model wrapper, tiling engine, scoring,
                         stitching (stitch.py), nucleus counting (cells.py)
backend/app/api/         REST endpoints
backend/app/worker.py    background analysis (one job at a time on the GPU)
backend/scripts/         Kather sample builder / seeder, foundation-model head training
frontend/src/pages/      QueueView (triage queue + upload), CaseView (viewer + review)
frontend/src/components/ SlideViewer (Leaflet CRS.Simple + heatmap overlay), UploadPanel, badges
```
