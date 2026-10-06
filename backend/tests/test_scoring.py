from app.inference.scoring import tier_for, urgency_score


def test_monotonic_in_tumor_fraction():
    scores = [urgency_score(f, 0.9, f, 0.0) for f in (0.0, 0.1, 0.3, 0.6, 1.0)]
    assert scores == sorted(scores)
    assert scores[0] < scores[-1]


def test_bounds_and_necrosis_bonus():
    assert urgency_score(0, 0, 0, 0) == 0
    assert urgency_score(1, 1, 1, 1) == 100
    # Necrosis only matters when tumor is present.
    assert urgency_score(0, 0.1, 0, 0.5) == urgency_score(0, 0.1, 0, 0)
    assert urgency_score(0.3, 0.9, 0.3, 0.2) > urgency_score(0.3, 0.9, 0.3, 0)


def test_tiers():
    assert tier_for(85) == "critical"
    assert tier_for(55) == "high"
    assert tier_for(5) == "routine"
