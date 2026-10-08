# Demo photos

Ready-made inputs for demos, so a new machine doesn't need to rebuild them. Regenerate with
`uv run python scripts/fetch_samples.py` (add `--seed` to upload them to a running backend, and
`--only single` or `--only mosaic` to upload just one kind).

| Path | Upload as | Shows |
| --- | --- | --- |
| `advanced_adenocarcinoma.jpg` | one photo | Critical: large tumor with necrosis |
| `invasive_focus.jpg` | one photo | High urgency |
| `mucinous_lesion.jpg` | one photo | Tumor in mucus |
| `small_suspicious_focus.jpg` | one photo | Small tumor focus |
| `inflamed_mucosa.jpg` | one photo | Benign, lymphocyte-rich |
| `normal_mucosa.jpg` | one photo | Routine, healthy colon lining |
| `mosaic_large_tumor/` | all 9 photos together | Stitching a 3×3 grid of overlapping fields |
| `mosaic_benign_mucosa/` | all 6 photos together | Stitching a benign slide |
| `mosaic_one_blurry_photo/` | all 6 photos together | Quality gate: one out-of-focus photo is left out |

These are not real phone photos. Each is composed from real H&E patches of the
[NCT-CRC-HE / CRC-VAL-HE-7K](https://zenodo.org/records/1214456) dataset (Kather et al., 2018,
CC BY 4.0), then given a simulated eyepiece look (soft focus, lamp tint, dark field ring). The
stitched sets are crops of one larger composed slide, overlapping by about a third, with slight
rotation and exposure changes between shots.
