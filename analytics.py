"""
analytics.py — Generates chart data for dashboards.
"""
from database.models import Student, Mark, Attendance, Subject, db
from sqlalchemy import func
import json


def get_student_grade_distribution(student_id):
    marks = Mark.query.filter_by(student_id=student_id).all()
    grade_counts = {}
    for m in marks:
        grade_counts[m.grade] = grade_counts.get(m.grade, 0) + 1
    return grade_counts


def get_student_semester_cgpa(student_id):
    """Returns list of (semester, avg_marks) for trend chart."""
    results = db.session.query(Mark.semester, func.avg(Mark.total))\
        .filter(Mark.student_id == student_id)\
        .group_by(Mark.semester).all()
    semesters = [f"Sem {r[0]}" for r in results]
    cgpas     = [round(r[1] / 10, 2) for r in results]
    return {"labels": semesters, "data": cgpas}


def get_attendance_summary(student_id):
    records = Attendance.query.filter_by(student_id=student_id).all()
    p = sum(1 for r in records if r.status == 'P')
    a = sum(1 for r in records if r.status == 'A')
    m = sum(1 for r in records if r.status == 'M')
    total = len(records) or 1
    return {"present": p, "absent": a, "medical": m, "pct": round(p / total * 100, 1)}


def get_subject_wise_marks(student_id):
    results = db.session.query(Subject.name, Mark.total)\
        .join(Mark, Mark.subject_id == Subject.id)\
        .filter(Mark.student_id == student_id).all()
    return {"labels": [r[0] for r in results], "data": [r[1] for r in results]}


def get_department_stats():
    total_students = Student.query.count()
    avg_cgpa       = db.session.query(func.avg(Student.cgpa)).scalar() or 0
    at_risk        = Student.query.filter(Student.risk_score > 0.55).count()
    avg_att        = db.session.query(func.avg(Student.attendance_pct)).scalar() or 0
    return {
        "total_students": total_students,
        "avg_cgpa": round(avg_cgpa, 2),
        "at_risk": at_risk,
        "avg_attendance": round(avg_att, 1),
    }


def get_class_marks_distribution(subject_id):
    marks = Mark.query.filter_by(subject_id=subject_id).all()
    buckets = {"0-40": 0, "40-60": 0, "60-75": 0, "75-90": 0, "90-100": 0}
    for m in marks:
        if m.total < 40:   buckets["0-40"] += 1
        elif m.total < 60: buckets["40-60"] += 1
        elif m.total < 75: buckets["60-75"] += 1
        elif m.total < 90: buckets["75-90"] += 1
        else:              buckets["90-100"] += 1
    return {"labels": list(buckets.keys()), "data": list(buckets.values())}
