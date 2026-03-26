from typing import Tuple

SEVERITY_RANK = {
    "low": 0,
    "mid": 1,
    "high": 2,
    "critical": 3,
}

RANK_TO_SEVERITY = {v: k for k, v in SEVERITY_RANK.items()}

def normalize_severity(severity: str) -> str:
    s = str(severity or "low").strip().lower()
    if s not in SEVERITY_RANK:
        return "low"
    return s

def promote(severity: str, steps: int = 1) -> str:
    s = normalize_severity(severity)
    new_rank = min(3, SEVERITY_RANK[s] + steps)
    return RANK_TO_SEVERITY[new_rank]

def attack_base_severity(label: str, confidence: float) -> str:
    u = str(label or "").upper()

    if u == "BENIGN":
        return "low"
    if confidence >= 0.97:
        return "high"
    if confidence >= 0.87:
        return "mid"
    return "low"

def fuse_severity_with_humans(
    base_severity: str,
    label: str,
    people_detected: int,
    motion_score: float,
) -> Tuple[str, str]:
    """
    Returns: (final_severity, reason)
    """
    base = normalize_severity(base_severity)

    if str(label or "").upper() == "BENIGN":
        return "low", "benign"

    if people_detected >= 6:
        return "critical", "crowd_detected"
    if people_detected >= 3:
        return promote(base, 1), "multiple_humans"
    if motion_score >= 0.35:
        return promote(base, 1), "high_motion"
    if motion_score >= 0.20:
        return promote(base, 0), "motion_present"

    return base, "normal_context"