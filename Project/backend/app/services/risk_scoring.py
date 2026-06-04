from __future__ import annotations

from dataclasses import dataclass


FACTOR_MAX_SCORES = {
    "past_sinkhole": 25.0,
    "gpr": 30.0,
    "facility": 15.0,
    "rainfall": 10.0,
    "groundwater": 7.0,
    "environment": 7.0,
    "construction": 6.0,
}

FACTOR_MULTIPLIERS = {
    "past_sinkhole": 8.0,
    "gpr": 12.0,
    "facility": 0.25,
    "rainfall": 1.0,
    "groundwater": 1.0,
    "environment": 1.0,
    "construction": 0.3,
}


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
        past_sinkhole=clamp(
            past_sinkhole_count * FACTOR_MULTIPLIERS["past_sinkhole"],
            0,
            FACTOR_MAX_SCORES["past_sinkhole"],
        ),
        gpr=clamp(
            gpr_detected_count * FACTOR_MULTIPLIERS["gpr"],
            0,
            FACTOR_MAX_SCORES["gpr"],
        ),
        facility=clamp(
            facility_aging_score * FACTOR_MULTIPLIERS["facility"],
            0,
            FACTOR_MAX_SCORES["facility"],
        ),
        rainfall=clamp(rainfall_score, 0, FACTOR_MAX_SCORES["rainfall"]),
        groundwater=clamp(groundwater_score, 0, FACTOR_MAX_SCORES["groundwater"]),
        environment=clamp(environment_score, 0, FACTOR_MAX_SCORES["environment"]),
        construction=clamp(
            construction_score * FACTOR_MULTIPLIERS["construction"],
            0,
            FACTOR_MAX_SCORES["construction"],
        ),
    )
    return clamp(breakdown.total), breakdown
