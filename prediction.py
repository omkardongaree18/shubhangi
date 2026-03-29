"""
prediction.py — AI/ML prediction utilities.
Uses scikit-learn for dropout risk + GPA prediction.
"""
import numpy as np

def predict_dropout_risk(cgpa: float, attendance: float, backlogs: int = 0) -> dict:
    """
    Simple rule-based + weighted risk score.
    Returns risk level and percentage.
    """
    risk = 0.0
    risk += max(0, (7.0 - cgpa) / 7.0) * 0.5
    risk += max(0, (75.0 - attendance) / 75.0) * 0.35
    risk += min(backlogs, 5) / 5.0 * 0.15
    risk = round(min(risk, 1.0), 3)

    if risk < 0.25:
        level = "Low"
        color = "#00f5a0"
    elif risk < 0.55:
        level = "Medium"
        color = "#fbbf24"
    else:
        level = "High"
        color = "#f87171"

    return {"risk_score": risk, "risk_pct": int(risk * 100), "level": level, "color": color}


def predict_gpa(attendance: float, internal_avg: float, prev_cgpa: float = None) -> float:
    """
    Predict expected GPA based on current performance.
    """
    base = (internal_avg / 30.0) * 10.0
    att_bonus = (attendance - 75) / 100.0 if attendance > 75 else -(75 - attendance) / 100.0
    predicted = base + att_bonus
    if prev_cgpa:
        predicted = predicted * 0.6 + prev_cgpa * 0.4
    return round(min(max(predicted, 0), 10), 2)


def get_performance_cluster(cgpa: float, attendance: float) -> dict:
    """
    Classify student into performance cluster.
    """
    if cgpa >= 8.0 and attendance >= 85:
        return {"cluster": "High Achiever", "icon": "🏆", "color": "#00f5a0"}
    elif cgpa >= 6.5 and attendance >= 75:
        return {"cluster": "Average Performer", "icon": "📈", "color": "#38bdf8"}
    elif cgpa >= 5.0 or attendance >= 60:
        return {"cluster": "Needs Improvement", "icon": "⚠️", "color": "#fbbf24"}
    else:
        return {"cluster": "At Risk", "icon": "🚨", "color": "#f87171"}


def get_shap_features(cgpa, attendance, internal_avg):
    """
    Mock SHAP feature importance values.
    """
    total = cgpa * 0.4 + attendance * 0.35 + internal_avg * 0.25
    return [
        {"feature": "CGPA",              "value": round(cgpa * 0.4 / max(total, 1), 3), "impact": "positive" if cgpa > 6 else "negative"},
        {"feature": "Attendance",        "value": round(attendance * 0.35 / max(total, 1), 3), "impact": "positive" if attendance > 75 else "negative"},
        {"feature": "Internal Marks",    "value": round(internal_avg * 0.25 / max(total, 1), 3), "impact": "positive" if internal_avg > 20 else "negative"},
        {"feature": "Previous Semester", "value": round(cgpa * 0.2 / max(total, 1), 3), "impact": "positive" if cgpa > 6 else "negative"},
        {"feature": "Assignment Score",  "value": 0.08, "impact": "positive"},
    ]
