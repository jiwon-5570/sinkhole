from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.models.schemas import WhatIfRequest
from app.services.risk_scoring import clamp, risk_level


FACTOR_LABELS = {
    "past_sinkhole": "과거 침하 이력",
    "gpr": "GPR 이상 신호",
    "facility": "시설물 노후도",
    "rainfall": "강우 영향",
    "groundwater": "지하수위 변화",
    "environment": "지반/환경 취약도",
    "construction": "굴착/공사 영향",
}


PRESETS: dict[str, dict[str, float | int | bool]] = {
    "heavy_rain": {
        "forecast_horizon_hours": 24,
        "extra_rainfall_mm": 120.0,
        "groundwater_delta_m": 0.4,
    },
    "typhoon": {
        "forecast_horizon_hours": 72,
        "extra_rainfall_mm": 220.0,
        "groundwater_delta_m": 0.8,
    },
    "excavation": {
        "forecast_horizon_hours": 168,
        "is_major_construction": True,
        "excavation_depth_m": 12.0,
        "construction_distance_m": 80.0,
    },
    "groundwater": {
        "forecast_horizon_hours": 72,
        "extra_rainfall_mm": 40.0,
        "groundwater_delta_m": 1.5,
    },
    "pipe_damage": {
        "forecast_horizon_hours": 24,
        "groundwater_delta_m": 0.7,
        "facility_aging_delta": 20.0,
        "gpr_anomaly_count": 2,
    },
}


@dataclass(frozen=True)
class Scenario:
    preset: str
    forecast_horizon_hours: int
    extra_rainfall_mm: float
    groundwater_delta_m: float
    is_major_construction: bool
    excavation_depth_m: float
    construction_distance_m: float
    gpr_anomaly_count: int
    facility_aging_delta: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "preset": self.preset,
            "forecast_horizon_hours": self.forecast_horizon_hours,
            "extra_rainfall_mm": round(self.extra_rainfall_mm, 1),
            "groundwater_delta_m": round(self.groundwater_delta_m, 2),
            "is_major_construction": self.is_major_construction,
            "excavation_depth_m": round(self.excavation_depth_m, 1),
            "construction_distance_m": round(self.construction_distance_m, 1),
            "gpr_anomaly_count": self.gpr_anomaly_count,
            "facility_aging_delta": round(self.facility_aging_delta, 1),
        }


def _max_number(request_value: float | int, preset_value: float | int | bool | None) -> float:
    if preset_value is None or isinstance(preset_value, bool):
        return float(request_value)
    return max(float(request_value), float(preset_value))


def normalize_scenario(req: WhatIfRequest) -> Scenario:
    preset_key = (req.scenario_preset or "custom").strip()
    preset = PRESETS.get(preset_key, {})
    return Scenario(
        preset=preset_key if preset_key in PRESETS else "custom",
        forecast_horizon_hours=max(int(req.forecast_horizon_hours), int(preset.get("forecast_horizon_hours", 0) or 0) or 1),
        extra_rainfall_mm=_max_number(req.extra_rainfall_mm, preset.get("extra_rainfall_mm")),
        groundwater_delta_m=max(float(req.groundwater_delta_m), float(preset.get("groundwater_delta_m", req.groundwater_delta_m))),
        is_major_construction=bool(req.is_major_construction or preset.get("is_major_construction", False)),
        excavation_depth_m=_max_number(req.excavation_depth_m, preset.get("excavation_depth_m")),
        construction_distance_m=min(float(req.construction_distance_m), float(preset.get("construction_distance_m", req.construction_distance_m))),
        gpr_anomaly_count=max(int(req.gpr_anomaly_count), int(preset.get("gpr_anomaly_count", req.gpr_anomaly_count))),
        facility_aging_delta=_max_number(req.facility_aging_delta, preset.get("facility_aging_delta")),
    )


def base_breakdown(row: dict) -> dict[str, float]:
    return {
        "past_sinkhole": clamp(float(row.get("past_sinkhole_count") or 0) * 8.0, 0, 30),
        "gpr": clamp(float(row.get("gpr_detected_count") or 0) * 12.0, 0, 30),
        "facility": clamp(float(row.get("facility_aging_score") or 0) * 0.25, 0, 15),
        "rainfall": clamp(float(row.get("rainfall_score") or 0), 0, 10),
        "groundwater": clamp(float(row.get("groundwater_score") or 0), 0, 8),
        "environment": clamp(float(row.get("environment_score") or 0), 0, 6),
        "construction": clamp(float(row.get("construction_score") or 0) * 0.2, 0, 4),
    }


def _horizon_factor(hours: int) -> float:
    if hours <= 6:
        return 0.65
    if hours <= 24:
        return 1.0
    if hours <= 72:
        return 1.22
    return 1.42


def simulated_breakdown(row: dict, scenario: Scenario) -> dict[str, float]:
    base = base_breakdown(row)
    horizon = _horizon_factor(scenario.forecast_horizon_hours)

    rainfall_add = clamp((scenario.extra_rainfall_mm / 18.0) * horizon, 0, 16)
    groundwater_add = clamp(abs(scenario.groundwater_delta_m) * 3.2 * horizon, 0, 10)
    gpr_add = clamp(scenario.gpr_anomaly_count * 4.0, 0, 14)
    facility_add = clamp(scenario.facility_aging_delta * 0.18, 0, 8)

    distance_factor = clamp((500.0 - scenario.construction_distance_m) / 500.0, 0, 1)
    depth_factor = clamp(scenario.excavation_depth_m / 20.0, 0, 1.6)
    construction_add = 0.0
    if scenario.is_major_construction or scenario.excavation_depth_m > 0:
        construction_add = clamp(3.0 + (distance_factor * 5.0) + (depth_factor * 3.0), 0, 12)

    return {
        "past_sinkhole": base["past_sinkhole"],
        "gpr": clamp(base["gpr"] + gpr_add, 0, 34),
        "facility": clamp(base["facility"] + facility_add, 0, 18),
        "rainfall": clamp(base["rainfall"] + rainfall_add, 0, 20),
        "groundwater": clamp(base["groundwater"] + groundwater_add, 0, 14),
        "environment": base["environment"],
        "construction": clamp(base["construction"] + construction_add, 0, 12),
    }


def _confidence(row: dict, scenario: Scenario) -> dict[str, Any]:
    required = [
        "past_sinkhole_count",
        "gpr_detected_count",
        "facility_aging_score",
        "rainfall_score",
        "groundwater_score",
        "environment_score",
    ]
    completeness = sum(1 for key in required if row.get(key) is not None) / len(required)
    horizon_penalty = 0.0 if scenario.forecast_horizon_hours <= 24 else 0.1 if scenario.forecast_horizon_hours <= 72 else 0.18
    stress_bonus = 0.05 if scenario.extra_rainfall_mm or scenario.groundwater_delta_m or scenario.is_major_construction else 0.0
    score = clamp((completeness * 0.82) + 0.13 + stress_bonus - horizon_penalty, 0.35, 0.96)
    label = "높음" if score >= 0.75 else "중간" if score >= 0.55 else "낮음"
    return {"score": round(score, 2), "label": label}


def _recommendations(score: float, diff: float, drivers: list[dict[str, Any]], scenario: Scenario) -> list[str]:
    items: list[str] = []
    driver_keys = {str(item.get("factor")) for item in drivers[:3]}
    if score >= 80 or diff >= 15:
        items.append("24시간 이내 현장 점검과 통제 필요 여부를 검토하세요.")
    elif score >= 60 or diff >= 8:
        items.append("우선 점검 대상으로 지정하고 센서 추이를 집중 모니터링하세요.")
    else:
        items.append("정기 모니터링을 유지하되 시나리오 변화가 커지면 재실행하세요.")
    if "rainfall" in driver_keys:
        items.append("배수 불량 구간, 맨홀 주변, 저지대 침수 가능성을 먼저 확인하세요.")
    if "groundwater" in driver_keys:
        items.append("지하수위 급변 센서와 주변 관정 자료를 교차 확인하세요.")
    if "construction" in driver_keys:
        items.append("굴착 깊이, 흙막이 상태, 공사장 배수 계획을 현장 확인하세요.")
    if "gpr" in driver_keys:
        items.append("GPR 이상 구간은 공동 재탐사 또는 내시경 조사를 검토하세요.")
    if scenario.forecast_horizon_hours >= 72:
        items.append("예측 기간이 길어질수록 불확실성이 커지므로 매일 재계산하세요.")
    return items[:5]


def simulate_region(row: dict, scenario: Scenario) -> dict[str, Any]:
    original_score = float(row.get("original_score") or 0.0)
    original_level = str(row.get("original_level") or risk_level(original_score))
    base = base_breakdown(row)
    simulated = simulated_breakdown(row, scenario)
    simulated_score = clamp(sum(simulated.values()), 0, 100)
    diff = simulated_score - original_score

    deltas = {
        key: round(simulated.get(key, 0.0) - base.get(key, 0.0), 1)
        for key in simulated
    }
    drivers = [
        {
            "factor": key,
            "label": FACTOR_LABELS.get(key, key),
            "delta": value,
            "score": round(simulated.get(key, 0.0), 1),
        }
        for key, value in sorted(deltas.items(), key=lambda item: item[1], reverse=True)
        if value > 0
    ]
    confidence = _confidence(row, scenario)
    new_level = risk_level(simulated_score)

    return {
        "region_id": int(row["region_id"]),
        "region_name": row["region_name"],
        "analysis_date": row.get("analysis_date"),
        "original_score": round(original_score, 1),
        "original_level": original_level,
        "simulated_score": round(simulated_score, 1),
        "score_diff": round(diff, 1),
        "new_risk_level": new_level,
        "level_changed": original_level != new_level,
        "priority_rank": int(row.get("priority_rank") or 0) or None,
        "confidence": confidence,
        "action_level": "긴급" if simulated_score >= 80 or diff >= 15 else "주의" if simulated_score >= 60 or diff >= 8 else "관찰",
        "breakdown": {key: round(value, 1) for key, value in simulated.items()},
        "breakdown_delta": deltas,
        "drivers": drivers[:4],
        "recommendations": _recommendations(simulated_score, diff, drivers, scenario),
        "scenario": scenario.as_dict(),
    }


def rank_simulation_results(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ranked = sorted(rows, key=lambda item: (-float(item["simulated_score"]), int(item["region_id"])))
    after_rank = {int(row["region_id"]): idx for idx, row in enumerate(ranked, start=1)}
    for row in rows:
        row["priority_after"] = after_rank[int(row["region_id"])]
        before = row.get("priority_rank")
        row["rank_change"] = None if before is None else int(before) - int(row["priority_after"])
    return sorted(rows, key=lambda item: (int(item["priority_after"]), int(item["region_id"])))
