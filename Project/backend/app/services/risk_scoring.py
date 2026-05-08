from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RiskBreakdown:
    past_sinkhole: float
    gpr: float
    facility: float
    rainfall: float
    groundwater: float
    environment: float
    construction: float

    @property
    def total(self) -> float:
        return (
            self.past_sinkhole
            + self.gpr
            + self.facility
            + self.rainfall
            + self.groundwater
            + self.environment
            + self.construction
        )


def risk_level(score_0_100: float) -> str:
    if score_0_100 < 30:
        return "\ub0ae\uc74c"
    if score_0_100 < 60:
        return "\ubcf4\ud1b5"
    if score_0_100 < 80:
        return "\ub192\uc74c"
    return "\ub9e4\uc6b0 \ub192\uc74c"


def clamp(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, v))


def score_rule_based(features: dict) -> tuple[float, RiskBreakdown]:
    past_sinkhole_count = float(features.get("past_sinkhole_count") or 0)
    gpr_detected_count = float(features.get("gpr_detected_count") or 0)
    facility_aging_score = float(features.get("facility_aging_score") or 0)
    rainfall_score = float(features.get("rainfall_score") or 0)
    groundwater_score = float(features.get("groundwater_score") or 0)
    environment_score = float(features.get("environment_score") or 0)
    construction_score = float(features.get("construction_score") or 0)

    breakdown = RiskBreakdown(
        past_sinkhole=clamp(past_sinkhole_count * 8.0, 0, 30),
        gpr=clamp(gpr_detected_count * 12.0, 0, 30),
        facility=clamp(facility_aging_score * 0.25, 0, 15),
        rainfall=clamp(rainfall_score, 0, 10),
        groundwater=clamp(groundwater_score, 0, 8),
        environment=clamp(environment_score, 0, 6),
        construction=clamp(construction_score * 0.2, 0, 4),
    )
    return clamp(breakdown.total), breakdown
