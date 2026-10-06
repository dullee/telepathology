from app import config


def urgency_score(
    tumor_fraction: float, max_tumor_prob: float, largest_region: float, necrosis_fraction: float
) -> float:
    """Combine tile-level evidence into a 0-100 triage score.

    tumor_fraction: share of tissue in suspicious areas (tumor, incl. its necrotic core).
    max_tumor_prob: strongest single-tile tumor probability.
    largest_region: largest contiguous suspicious area as a share of tissue.
    necrosis_fraction: share of tissue tiles that are debris/necrosis (tumor-associated).
    """
    w = config.URGENCY_WEIGHTS
    score = 100 * (
        w["tumor_fraction"] * tumor_fraction
        + w["max_tumor_prob"] * max_tumor_prob
        + w["largest_region"] * largest_region
    )
    if tumor_fraction > 0:
        score += config.NECROSIS_BONUS * min(1.0, necrosis_fraction * 4)
    return round(max(0.0, min(100.0, score)), 1)


def tier_for(score: float) -> str:
    for cutoff, name in config.TIERS:
        if score >= cutoff:
            return name
    return "routine"
