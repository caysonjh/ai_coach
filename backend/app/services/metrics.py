from app.models.entities import MetricType


METRIC_DEFINITIONS: dict[MetricType, dict[str, str]] = {
    MetricType.sleep_score: {"label": "Sleep Score", "unit": "score"},
    MetricType.sleep_duration_hours: {"label": "Sleep Duration", "unit": "hours"},
    MetricType.hrv_ms: {"label": "HRV", "unit": "ms"},
    MetricType.hrv_status: {"label": "HRV Status", "unit": "status"},
    MetricType.resting_hr: {"label": "Resting Heart Rate", "unit": "bpm"},
    MetricType.vo2_max: {"label": "VO2 Max", "unit": "ml/kg/min"},
    MetricType.ftp: {"label": "FTP", "unit": "watts"},
    MetricType.training_readiness: {"label": "Training Readiness", "unit": "score"},
    MetricType.training_status: {"label": "Training Status", "unit": "status"},
    MetricType.acute_load: {"label": "Acute Load", "unit": "load"},
    MetricType.load_ratio: {"label": "Load Ratio", "unit": "ratio"},
    MetricType.load_focus: {"label": "Load Focus", "unit": "category"},
    MetricType.recovery_time_hours: {"label": "Recovery Time", "unit": "hours"},
    MetricType.aerobic_training_effect: {"label": "Aerobic Training Effect", "unit": "score"},
    MetricType.anaerobic_training_effect: {"label": "Anaerobic Training Effect", "unit": "score"},
    MetricType.endurance_score: {"label": "Endurance Score", "unit": "score"},
    MetricType.hill_score: {"label": "Hill Score", "unit": "score"},
    MetricType.lactate_threshold_hr: {"label": "Lactate Threshold HR", "unit": "bpm"},
    MetricType.lactate_threshold_pace: {"label": "Lactate Threshold Pace", "unit": "sec/km"},
    MetricType.lactate_threshold_power: {"label": "Lactate Threshold Power", "unit": "watts"},
    MetricType.body_battery: {"label": "Body Battery", "unit": "score"},
    MetricType.stress: {"label": "Stress", "unit": "score"},
    MetricType.pulse_ox: {"label": "Pulse Ox", "unit": "%"},
    MetricType.respiration_rate: {"label": "Respiration Rate", "unit": "brpm"},
    MetricType.body_weight: {"label": "Body Weight", "unit": "lb"},
    MetricType.body_fat_percent: {"label": "Body Fat", "unit": "%"},
    MetricType.heat_acclimation: {"label": "Heat Acclimation", "unit": "%"},
    MetricType.altitude_acclimation: {"label": "Altitude Acclimation", "unit": "m"},
    MetricType.fatigue_note: {"label": "Fatigue Note", "unit": "note"},
    MetricType.rcpd_symptom_note: {"label": "R-CPD Symptom Note", "unit": "note"},
    MetricType.custom: {"label": "Custom", "unit": "custom"},
}


def metric_options() -> list[dict[str, str]]:
    return [
        {"value": metric.value, "label": definition["label"], "unit": definition["unit"]}
        for metric, definition in METRIC_DEFINITIONS.items()
    ]
