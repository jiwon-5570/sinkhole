from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.models.schemas import WhatIfRequest
from app.services.risk_scoring import clamp, risk_level


FACTOR_LABELS = {
    "past_sinkhole": "과거 지반침하 이력",
    "gpr": "GPR 이상 신호",
    "facility": "시설물/노후건물",
    "rainfall": "강우 영향",
    "groundwater": "지하수위 변화",
    "environment": "지층/환경 취약도",
    "construction": "굴착/공사 영향",
}


MITIGATION_LABELS = {
    "mitigation_gpr_survey": "GPR 정밀탐사 및 공동 확인",
    "mitigation_pipe_repair": "노후/손상 관로 보수",
    "mitigation_drainage": "배수 정비 및 침수 저감",
    "mitigation_construction_control": "굴착공사 품질·배수 관리",
    "mitigation_monitoring": "모니터링 지점 추가",
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
    "old_building": {
        "forecast_horizon_hours": 72,
        "facility_aging_delta": 30.0,
        "environment_delta_score": 2.0,
    },
    "compound": {
        "forecast_horizon_hours": 72,
        "extra_rainfall_mm": 120.0,
        "groundwater_delta_m": 0.8,
        "is_major_construction": True,
        "excavation_depth_m": 10.0,
        "construction_distance_m": 120.0,
        "gpr_anomaly_count": 2,
        "facility_aging_delta": 20.0,
        "past_sinkhole_delta_count": 1,
        "environment_delta_score": 2.5,
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
    past_sinkhole_delta_count: int
    environment_delta_score: float
    mitigation_gpr_survey: bool
    mitigation_pipe_repair: bool
    mitigation_drainage: bool
    mitigation_construction_control: bool
    mitigation_monitoring: bool

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
            "past_sinkhole_delta_count": self.past_sinkhole_delta_count,
            "environment_delta_score": round(self.environment_delta_score, 1),
            "mitigation_gpr_survey": self.mitigation_gpr_survey,
            "mitigation_pipe_repair": self.mitigation_pipe_repair,
            "mitigation_drainage": self.mitigation_drainage,
            "mitigation_construction_control": self.mitigation_construction_control,
            "mitigation_monitoring": self.mitigation_monitoring,
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
        forecast_horizon_hours=max(
            int(req.forecast_horizon_hours),
            int(preset.get("forecast_horizon_hours", 0) or 0) or 1,
        ),
        extra_rainfall_mm=_max_number(req.extra_rainfall_mm, preset.get("extra_rainfall_mm")),
        groundwater_delta_m=max(
            float(req.groundwater_delta_m),
            float(preset.get("groundwater_delta_m", req.groundwater_delta_m)),
        ),
        is_major_construction=bool(req.is_major_construction or preset.get("is_major_construction", False)),
        excavation_depth_m=_max_number(req.excavation_depth_m, preset.get("excavation_depth_m")),
        construction_distance_m=min(
            float(req.construction_distance_m),
            float(preset.get("construction_distance_m", req.construction_distance_m)),
        ),
        gpr_anomaly_count=max(int(req.gpr_anomaly_count), int(preset.get("gpr_anomaly_count", req.gpr_anomaly_count))),
        facility_aging_delta=_max_number(req.facility_aging_delta, preset.get("facility_aging_delta")),
        past_sinkhole_delta_count=max(
            int(req.past_sinkhole_delta_count),
            int(preset.get("past_sinkhole_delta_count", req.past_sinkhole_delta_count)),
        ),
        environment_delta_score=_max_number(req.environment_delta_score, preset.get("environment_delta_score")),
        mitigation_gpr_survey=bool(req.mitigation_gpr_survey),
        mitigation_pipe_repair=bool(req.mitigation_pipe_repair),
        mitigation_drainage=bool(req.mitigation_drainage),
        mitigation_construction_control=bool(req.mitigation_construction_control),
        mitigation_monitoring=bool(req.mitigation_monitoring),
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
    past_sinkhole_add = clamp(scenario.past_sinkhole_delta_count * 8.0, 0, 24)
    environment_add = clamp(scenario.environment_delta_score, 0, 10)

    distance_factor = clamp((500.0 - scenario.construction_distance_m) / 500.0, 0, 1)
    depth_factor = clamp(scenario.excavation_depth_m / 20.0, 0, 1.6)
    construction_add = 0.0
    if scenario.is_major_construction or scenario.excavation_depth_m > 0:
        construction_add = clamp(3.0 + (distance_factor * 5.0) + (depth_factor * 3.0), 0, 12)

    return {
        "past_sinkhole": clamp(base["past_sinkhole"] + past_sinkhole_add, 0, 34),
        "gpr": clamp(base["gpr"] + gpr_add, 0, 34),
        "facility": clamp(base["facility"] + facility_add, 0, 18),
        "rainfall": clamp(base["rainfall"] + rainfall_add, 0, 20),
        "groundwater": clamp(base["groundwater"] + groundwater_add, 0, 14),
        "environment": clamp(base["environment"] + environment_add, 0, 12),
        "construction": clamp(base["construction"] + construction_add, 0, 12),
    }


def _mitigation_flags(scenario: Scenario) -> dict[str, bool]:
    return {
        "mitigation_gpr_survey": scenario.mitigation_gpr_survey,
        "mitigation_pipe_repair": scenario.mitigation_pipe_repair,
        "mitigation_drainage": scenario.mitigation_drainage,
        "mitigation_construction_control": scenario.mitigation_construction_control,
        "mitigation_monitoring": scenario.mitigation_monitoring,
    }


def _active_mitigation_labels(scenario: Scenario) -> list[str]:
    return [MITIGATION_LABELS[key] for key, enabled in _mitigation_flags(scenario).items() if enabled]


def _reduce_factor(
    values: dict[str, float],
    effects: list[dict[str, Any]],
    factor: str,
    amount: float,
    action_key: str,
    reason: str,
) -> None:
    before = float(values.get(factor) or 0.0)
    actual = clamp(min(before, max(0.0, amount)), 0, 100)
    if actual <= 0:
        return
    values[factor] = round(before - actual, 3)
    effects.append(
        {
            "action_key": action_key,
            "action_label": MITIGATION_LABELS.get(action_key, action_key),
            "factor": factor,
            "factor_label": FACTOR_LABELS.get(factor, factor),
            "reduction": round(actual, 1),
            "reason": reason,
        }
    )


def apply_mitigation(breakdown: dict[str, float], scenario: Scenario) -> tuple[dict[str, float], list[dict[str, Any]]]:
    adjusted = dict(breakdown)
    effects: list[dict[str, Any]] = []

    if scenario.mitigation_gpr_survey:
        _reduce_factor(
            adjusted,
            effects,
            "gpr",
            max(2.0, float(adjusted.get("gpr") or 0.0) * 0.35),
            "mitigation_gpr_survey",
            "GPR 정밀탐사로 공동 후보를 확인·보수 대상으로 분리해 탐지 불확실성을 낮춘 것으로 반영",
        )

    if scenario.mitigation_pipe_repair:
        _reduce_factor(
            adjusted,
            effects,
            "facility",
            3.0,
            "mitigation_pipe_repair",
            "노후 또는 손상 관로 보수로 시설물 노후 위험의 일부를 낮춘 것으로 반영",
        )
        _reduce_factor(
            adjusted,
            effects,
            "groundwater",
            2.0,
            "mitigation_pipe_repair",
            "누수·침투수 가능성을 낮춰 지하수/토사 유실 관련 잔여 위험을 낮춘 것으로 반영",
        )

    if scenario.mitigation_drainage:
        _reduce_factor(
            adjusted,
            effects,
            "rainfall",
            3.0,
            "mitigation_drainage",
            "배수 정비로 강우 직후 표면수 유입과 침수 위험을 낮춘 것으로 반영",
        )
        _reduce_factor(
            adjusted,
            effects,
            "groundwater",
            1.0,
            "mitigation_drainage",
            "배수 개선으로 지하수위 급변에 따른 추가 위험을 일부 낮춘 것으로 반영",
        )

    if scenario.mitigation_construction_control:
        _reduce_factor(
            adjusted,
            effects,
            "construction",
            4.0,
            "mitigation_construction_control",
            "굴착 현장의 흙막이·되메우기·배수 관리가 강화된 것으로 반영",
        )

    return adjusted, effects


def _mitigation_no_score_notes(scenario: Scenario, effects: list[dict[str, Any]]) -> list[str]:
    notes: list[str] = []
    active_effect_keys = {str(item.get("action_key")) for item in effects}
    if scenario.mitigation_monitoring:
        notes.append("모니터링 지점 추가는 위험을 직접 제거하지는 않지만, 이상 징후 발견 가능성과 운영 신뢰도를 높이는 조치로 반영했습니다.")
    for key, enabled in _mitigation_flags(scenario).items():
        if enabled and key != "mitigation_monitoring" and key not in active_effect_keys:
            notes.append(f"{MITIGATION_LABELS.get(key, key)}은 선택됐지만 현재 해당 요인 점수가 낮아 추가 감점은 적용되지 않았습니다.")
    return notes


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
    mitigation_bonus = 0.0
    if scenario.mitigation_monitoring:
        mitigation_bonus += 0.04
    if scenario.mitigation_gpr_survey:
        mitigation_bonus += 0.03
    score = clamp((completeness * 0.82) + 0.13 + stress_bonus + min(mitigation_bonus, 0.07) - horizon_penalty, 0.35, 0.98)
    label = "높음" if score >= 0.75 else "중간" if score >= 0.55 else "낮음"
    return {"score": round(score, 2), "label": label}


def _data_quality(row: dict, scenario: Scenario) -> dict[str, Any]:
    factor_sources = [
        ("past_sinkhole_count", "과거 사고"),
        ("gpr_detected_count", "GPR/탐사"),
        ("facility_aging_score", "시설물/노후건물"),
        ("rainfall_score", "강우"),
        ("groundwater_score", "지하수"),
        ("environment_score", "지층/환경"),
        ("construction_score", "공사"),
    ]
    available = [label for key, label in factor_sources if row.get(key) is not None]
    missing = [label for key, label in factor_sources if row.get(key) is None]
    ratio = len(available) / len(factor_sources)
    label = "높음" if ratio >= 0.85 else "보통" if ratio >= 0.6 else "낮음"
    limitations: list[str] = []
    if scenario.forecast_horizon_hours > 72:
        limitations.append("예측 기간이 72시간을 넘으면 기상·지하수 조건의 불확실성이 커집니다.")
    if scenario.gpr_anomaly_count and row.get("gpr_detected_count") is None:
        limitations.append("GPR 이상 신호는 사용자가 입력한 시나리오 값이며, 실제 탐사 확정값이 아닙니다.")
    if scenario.is_major_construction and row.get("construction_score") is None:
        limitations.append("공사 영향은 사용자 시나리오 값 중심으로 반영됐습니다.")
    if _active_mitigation_labels(scenario):
        limitations.append("관리 조치 감점은 조치가 실제 완료됐다고 가정한 운영 시뮬레이션입니다.")
    return {
        "label": label,
        "available_factors": available,
        "missing_factors": missing,
        "basis": f"{len(available)}/{len(factor_sources)}개 핵심 요인에 정규화된 값이 있습니다.",
        "limitations": limitations,
    }


def _factor_changes(
    base: dict[str, float],
    scenario_breakdown: dict[str, float],
    final_breakdown: dict[str, float],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for key in FACTOR_LABELS:
        base_value = float(base.get(key) or 0.0)
        scenario_value = float(scenario_breakdown.get(key) or 0.0)
        final_value = float(final_breakdown.get(key) or 0.0)
        rows.append(
            {
                "factor": key,
                "label": FACTOR_LABELS.get(key, key),
                "base": round(base_value, 1),
                "scenario": round(scenario_value, 1),
                "final": round(final_value, 1),
                "increase": round(scenario_value - base_value, 1),
                "mitigation": round(scenario_value - final_value, 1),
                "net_delta": round(final_value - base_value, 1),
            }
        )
    return rows


def _ai_commentary(
    region_name: str,
    original_score: float,
    scenario_score: float,
    final_score: float,
    original_level: str,
    final_level: str,
    drivers: list[dict[str, Any]],
    effects: list[dict[str, Any]],
    scenario: Scenario,
    data_quality: dict[str, Any],
) -> str:
    driver_text = ", ".join(
        f"{item['label']} +{float(item['delta']):.1f}점"
        for item in drivers[:3]
    ) or "뚜렷한 추가 상승 요인 없음"
    mitigation_text = ", ".join(
        f"{item['action_label']}({item['factor_label']} -{float(item['reduction']):.1f}점)"
        for item in effects[:3]
    ) or "선택된 감점 조치 없음"
    horizon_text = f"{scenario.forecast_horizon_hours}시간"
    return (
        f"{region_name}은 현재 {original_score:.1f}점({original_level})에서 {horizon_text} 시나리오 적용 시 "
        f"{scenario_score:.1f}점까지 변합니다. 주요 상승 요인은 {driver_text}입니다. "
        f"선택한 관리 조치를 반영한 조치 후 점수는 {final_score:.1f}점({final_level})이며, "
        f"반영된 조치는 {mitigation_text}입니다. 데이터 충분성은 {data_quality['label']}({data_quality['basis']})입니다. "
        "추측: 이 결과는 현재 DB의 공공데이터와 사용자가 입력한 What-If 조건을 결합한 운영 시뮬레이션이며, 실제 위험 확정은 현장 점검과 최신 센서/탐사 데이터로 확인해야 합니다."
    )


def _recommendations(
    score: float,
    diff: float,
    drivers: list[dict[str, Any]],
    scenario: Scenario,
    effects: list[dict[str, Any]] | None = None,
) -> list[str]:
    items: list[str] = []
    driver_keys = {str(item.get("factor")) for item in drivers[:3]}
    effects = effects or []
    if score >= 80 or diff >= 15:
        items.append("24시간 이내 현장 점검과 통제 필요 여부를 검토하세요.")
    elif score >= 60 or diff >= 8:
        items.append("우선 점검 대상으로 지정하고 일별 추이를 집중 모니터링하세요.")
    else:
        items.append("정기 모니터링을 유지하되 시나리오 변화가 커지면 재실행하세요.")
    if "rainfall" in driver_keys:
        items.append("배수 불량 구간, 맨홀 주변, 저지대 침수 가능성을 먼저 확인하세요.")
    if "groundwater" in driver_keys:
        items.append("지하수위 급변 이력과 주변 관측 자료를 교차 확인하세요.")
    if "construction" in driver_keys:
        items.append("굴착 깊이, 흙막이 상태, 공사장 배수 계획을 현장 확인하세요.")
    if "gpr" in driver_keys:
        items.append("GPR 이상 구간은 공동 탐사 또는 내시경 조사를 검토하세요.")
    if "facility" in driver_keys:
        items.append("노후 건물과 관로 밀집 구간의 누수, 균열, 배수 상태를 점검하세요.")
    if "past_sinkhole" in driver_keys:
        items.append("반복 침하 이력이 반영된 구간은 보수 이력과 지하시설물 도면을 함께 확인하세요.")
    if "environment" in driver_keys:
        items.append("취약 지층 또는 매립층이 의심되는 구간은 시추/GPR 재검증 우선순위를 높이세요.")
    if scenario.forecast_horizon_hours >= 72:
        items.append("예측 기간이 길어질수록 불확실성이 커지므로 매일 재계산하세요.")
    if effects:
        labels = ", ".join(str(item.get("action_label")) for item in effects[:2])
        items.append(f"선택한 관리 조치({labels})의 완료 여부를 현장 기록으로 확인한 뒤 재분석하세요.")
    return items[:5]


def simulate_region(row: dict, scenario: Scenario) -> dict[str, Any]:
    original_score = float(row.get("original_score") or 0.0)
    original_level = str(row.get("original_level") or risk_level(original_score))
    base = base_breakdown(row)
    scenario_breakdown = simulated_breakdown(row, scenario)
    scenario_score = clamp(sum(scenario_breakdown.values()), 0, 100)
    simulated, mitigation_effects = apply_mitigation(scenario_breakdown, scenario)
    simulated_score = clamp(sum(simulated.values()), 0, 100)
    diff = simulated_score - original_score
    scenario_diff = scenario_score - original_score
    mitigation_reduction = scenario_score - simulated_score

    scenario_deltas = {
        key: round(scenario_breakdown.get(key, 0.0) - base.get(key, 0.0), 1)
        for key in scenario_breakdown
    }
    final_deltas = {
        key: round(simulated.get(key, 0.0) - base.get(key, 0.0), 1)
        for key in scenario_breakdown
    }
    drivers = [
        {
            "factor": key,
            "label": FACTOR_LABELS.get(key, key),
            "delta": value,
            "score": round(scenario_breakdown.get(key, 0.0), 1),
        }
        for key, value in sorted(scenario_deltas.items(), key=lambda item: item[1], reverse=True)
        if value > 0
    ]
    confidence = _confidence(row, scenario)
    new_level = risk_level(simulated_score)
    data_quality = _data_quality(row, scenario)
    factor_changes = _factor_changes(base, scenario_breakdown, simulated)
    no_score_notes = _mitigation_no_score_notes(scenario, mitigation_effects)
    ai_commentary = _ai_commentary(
        str(row.get("region_name") or "-"),
        original_score,
        scenario_score,
        simulated_score,
        original_level,
        new_level,
        drivers,
        mitigation_effects,
        scenario,
        data_quality,
    )

    return {
        "region_id": int(row["region_id"]),
        "region_name": row["region_name"],
        "analysis_date": row.get("analysis_date"),
        "original_score": round(original_score, 1),
        "original_level": original_level,
        "scenario_score_before_mitigation": round(scenario_score, 1),
        "scenario_score_diff": round(scenario_diff, 1),
        "simulated_score": round(simulated_score, 1),
        "score_diff": round(diff, 1),
        "mitigation_reduction": round(mitigation_reduction, 1),
        "new_risk_level": new_level,
        "level_changed": original_level != new_level,
        "priority_rank": int(row.get("priority_rank") or 0) or None,
        "confidence": confidence,
        "action_level": "긴급" if simulated_score >= 80 or diff >= 15 else "주의" if simulated_score >= 60 or diff >= 8 else "관찰",
        "scenario_breakdown": {key: round(value, 1) for key, value in scenario_breakdown.items()},
        "breakdown": {key: round(value, 1) for key, value in simulated.items()},
        "breakdown_delta": final_deltas,
        "scenario_breakdown_delta": scenario_deltas,
        "factor_changes": factor_changes,
        "drivers": drivers[:5],
        "mitigation_effects": mitigation_effects,
        "mitigation_notes": no_score_notes,
        "active_mitigations": _active_mitigation_labels(scenario),
        "data_quality": data_quality,
        "ai_commentary": ai_commentary,
        "recommendations": _recommendations(simulated_score, diff, drivers, scenario, mitigation_effects),
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
