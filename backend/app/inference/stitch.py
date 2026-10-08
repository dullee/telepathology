"""Stitch overlapping eyepiece photos of one slide into a single mosaic.

The clinician moves the stage between photos so neighbouring fields overlap (about a third).
Each photo is a lit disc inside the dark eyepiece ring, so:

1. Find SIFT features inside each disc only (`field_mask`) and match every pair of photos.
2. Fit a similarity transform (shift + rotation + uniform scale) per matching pair with RANSAC.
   A flat slide under a fixed objective needs nothing more flexible.
3. Chain photos to one reference along the strongest matches (a maximum spanning tree).
4. Blend with weights that fall to zero at the eyepiece edge, so the dark ring and the dim
   field-stop never show and seams fade out.

Areas outside every field stay black, which the engine already treats as non-tissue.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from PIL import Image
from scipy import ndimage

from app import config

MATCH_SIDE = 1024  # photos are matched at this size; transforms are scaled back up
MIN_INLIERS = 25


class StitchError(ValueError):
    """Photos could not be aligned (too little overlap, blur, or not the same slide)."""


@dataclass
class Mosaic:
    image: Image.Image
    used: int  # photos that made it into the mosaic
    total: int
    downscale: float  # < 1 when the mosaic was shrunk to fit MOSAIC_MAX_SIDE


def field_mask(arr: np.ndarray) -> np.ndarray:
    """True inside the illuminated eyepiece field, minus its dim rim.

    The field stop is a convex disc, so the mask is the convex hull of the lit area: dark tissue
    (dense nuclei) touching the field edge stays inside instead of being cut out as 'ring'."""
    gray = cv2.GaussianBlur(cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY), (0, 0), 3).astype(np.float32)
    lit = gray > max(25.0, 0.3 * float(np.percentile(gray, 90)))
    labels, n = ndimage.label(lit)
    if n == 0:
        return np.zeros(gray.shape, bool)
    disc = (labels == np.argmax(np.bincount(labels.ravel())[1:]) + 1).astype(np.uint8)
    contours, _ = cv2.findContours(disc, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    hull = np.zeros_like(disc)
    cv2.fillPoly(hull, [cv2.convexHull(np.concatenate(contours))], 1)
    # Pull in from the field stop: its soft, dim edge would tint the blend.
    r = max(3, round(0.03 * max(arr.shape[:2])))
    return cv2.erode(hull, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1))) > 0


def _features(arr: np.ndarray, mask: np.ndarray, sift) -> tuple[list, np.ndarray | None, float]:
    s = min(1.0, MATCH_SIDE / max(arr.shape[:2]))
    small = cv2.resize(arr, None, fx=s, fy=s, interpolation=cv2.INTER_AREA) if s < 1 else arr
    m = cv2.resize(mask.astype(np.uint8), (small.shape[1], small.shape[0]), interpolation=cv2.INTER_NEAREST)
    kp, desc = sift.detectAndCompute(cv2.cvtColor(small, cv2.COLOR_RGB2GRAY), m)
    return kp, desc, s


def _pair(fa, fb, matcher) -> tuple[np.ndarray, int] | None:
    """Similarity transform mapping photo b's full-res pixels into photo a's, and its inlier count."""
    (ka, da, sa), (kb, db, sb) = fa, fb
    if da is None or db is None or len(ka) < MIN_INLIERS or len(kb) < MIN_INLIERS:
        return None
    good = [m for m, n in (p for p in matcher.knnMatch(db, da, k=2) if len(p) == 2) if m.distance < 0.75 * n.distance]
    if len(good) < MIN_INLIERS:
        return None
    src = np.float32([kb[m.queryIdx].pt for m in good]) / sb
    dst = np.float32([ka[m.trainIdx].pt for m in good]) / sa
    M, inl = cv2.estimateAffinePartial2D(src, dst, method=cv2.RANSAC, ransacReprojThreshold=4.0)
    if M is None or int(inl.sum()) < MIN_INLIERS:
        return None
    scale = float(np.hypot(M[0, 0], M[1, 0]))
    if not 0.9 < scale < 1.1:  # same objective: anything else is a false match
        return None
    return np.vstack([M, [0, 0, 1]]), int(inl.sum())


def _layout(n: int, edges: dict[tuple[int, int], tuple[np.ndarray, int]]) -> dict[int, np.ndarray]:
    """Grow a maximum spanning tree from the best-connected photo; return photo -> reference transforms."""
    score = np.zeros(n)
    for (i, j), (_, w) in edges.items():
        score[i] += w
        score[j] += w
    root = int(np.argmax(score))
    placed = {root: np.eye(3)}
    while True:
        best = None
        for (i, j), (M, w) in edges.items():  # M maps j -> i
            if i in placed and j not in placed:
                cand = (w, j, placed[i] @ M)
            elif j in placed and i not in placed:
                cand = (w, i, placed[j] @ np.linalg.inv(M))
            else:
                continue
            if best is None or cand[0] > best[0]:
                best = cand
        if best is None:
            return placed
        placed[best[1]] = best[2]


def stitch(images: list[Image.Image]) -> Mosaic:
    """Images should already be EXIF-rotated RGB at the analysis scale (see prepare_image)."""
    if len(images) < 2:
        raise StitchError("Stitching needs at least two overlapping photos.")
    arrs = [np.asarray(im.convert("RGB")) for im in images]
    masks = [field_mask(a) for a in arrs]

    sift = cv2.SIFT_create(nfeatures=4000)
    feats = [_features(a, m, sift) for a, m in zip(arrs, masks)]
    matcher = cv2.BFMatcher(cv2.NORM_L2)
    edges = {}
    for i in range(len(arrs)):
        for j in range(i + 1, len(arrs)):
            if (res := _pair(feats[i], feats[j], matcher)) is not None:
                edges[(i, j)] = res
    placed = _layout(len(arrs), edges)
    if len(placed) < 2:
        raise StitchError(
            "Couldn't line the photos up. Overlap each photo with the previous one by about a "
            "third, keep the same magnification and focus, and avoid empty glass."
        )

    # Canvas covering every placed photo, shrunk if it would exceed MOSAIC_MAX_SIDE.
    corners = []
    for i, M in placed.items():
        h, w = arrs[i].shape[:2]
        pts = np.float32([[0, 0, 1], [w, 0, 1], [0, h, 1], [w, h, 1]]) @ M.T
        corners.append(pts[:, :2])
    corners = np.concatenate(corners)
    lo, hi = corners.min(axis=0), corners.max(axis=0)
    scale = min(1.0, (config.MOSAIC_MAX_SIDE - 1) / float((hi - lo).max()))  # canvas is extent + 1 px
    shift = np.array([[scale, 0, -lo[0] * scale], [0, scale, -lo[1] * scale], [0, 0, 1]])
    W, H = (np.ceil((hi - lo) * scale).astype(int) + 1).tolist()

    acc = np.zeros((H, W, 3), np.float32)
    wsum = np.zeros((H, W), np.float32)
    for i, M in placed.items():
        A = (shift @ M)[:2]
        # Weight peaks in the field centre and reaches zero at its edge.
        dist = cv2.distanceTransform(masks[i].astype(np.uint8), cv2.DIST_L2, 5)
        weight = cv2.warpAffine(dist / max(dist.max(), 1), A, (W, H), flags=cv2.INTER_LINEAR)
        warped = cv2.warpAffine(arrs[i], A, (W, H), flags=cv2.INTER_LINEAR)
        acc += warped.astype(np.float32) * weight[..., None]
        wsum += weight
    out = np.where(wsum[..., None] > 1e-3, acc / np.maximum(wsum, 1e-6)[..., None], 0)
    image = Image.fromarray(np.clip(out, 0, 255).astype(np.uint8))
    return Mosaic(image=image, used=len(placed), total=len(images), downscale=round(scale, 4))


def field_paths(case_dir: Path) -> list[Path]:
    return sorted(case_dir.glob("field_*"))
