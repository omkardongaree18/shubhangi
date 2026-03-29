from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, send_file
import sqlite3, hashlib, os, random, json, io
from datetime import date, datetime, timedelta
from functools import wraps
from db_setup import get_db, hash_password, init_db, DB_PATH

app = Flask(__name__)
app.secret_key = 'college_acad_mgmt_secret_2026'
@app.route("/")
def home():
    return "App working 🚀"

# ── DECORATORS ────────────────────────────────────────────────────
def login_required(role=None):
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            if 'user_id' not in session:
                flash('Please login first.', 'error')
                return redirect(url_for('login'))
            if role and session.get('role') != role:
                flash('Access denied.', 'error')
                return redirect(url_for('login'))
            return f(*args, **kwargs)
        return wrapper
    return decorator

# ── HELPERS ──────────────────────────────────────────────────────
def compute_cgpa(sid):
    db = get_db()
    rows = db.execute("SELECT total FROM marks WHERE student_id=?", (sid,)).fetchall()
    db.close()
    if not rows: return 0.0
    return round(min(10.0, sum(r['total'] for r in rows) / len(rows) / 10.0), 2)

def compute_dropout_risk(sid):
    db = get_db()
    marks = db.execute("SELECT total FROM marks WHERE student_id=?", (sid,)).fetchall()
    att   = db.execute("SELECT status FROM attendance WHERE student_id=?", (sid,)).fetchall()
    db.close()
    risk = 0.0
    if marks:
        avg = sum(r['total'] for r in marks) / len(marks)
        risk += 0.40 if avg < 50 else (0.20 if avg < 65 else (0.10 if avg < 75 else 0))
    if att:
        pct = sum(1 for a in att if a['status'] == 'P') / len(att) * 100
        risk += 0.40 if pct < 60 else (0.22 if pct < 75 else (0.08 if pct < 85 else 0))
    return round(min(0.97, risk), 3)

def get_att_pct(sid):
    db = get_db()
    rows = db.execute("SELECT status FROM attendance WHERE student_id=?", (sid,)).fetchall()
    db.close()
    if not rows: return 0.0
    return round(sum(1 for r in rows if r['status'] == 'P') / len(rows) * 100, 1)

def risk_info(r):
    if r >= 0.55: return 'High',   '#f87171'
    if r >= 0.25: return 'Medium', '#fbbf24'
    return 'Low', '#00f5a0'

def get_grade(t):
    return 'O' if t >= 90 else ('A+' if t >= 75 else ('A' if t >= 60 else ('B' if t >= 50 else ('C' if t >= 40 else 'F'))))

def recalc(sid, db):
    marks = db.execute("SELECT total FROM marks WHERE student_id=?", (sid,)).fetchall()
    att   = db.execute("SELECT status FROM attendance WHERE student_id=?", (sid,)).fetchall()
    cgpa  = round(sum(r['total'] for r in marks) / max(len(marks), 1) / 10.0, 2) if marks else 0.0
    pct   = sum(1 for a in att if a['status'] == 'P') / max(len(att), 1) * 100
    risk  = 0.0
    if marks:
        avg = sum(r['total'] for r in marks) / len(marks)
        risk += 0.40 if avg < 50 else (0.20 if avg < 65 else (0.10 if avg < 75 else 0))
    if att:
        risk += 0.40 if pct < 60 else (0.22 if pct < 75 else (0.08 if pct < 85 else 0))
    db.execute("UPDATE students SET cgpa=?,dropout_risk=? WHERE id=?",
               (round(min(cgpa, 10.0), 2), round(min(risk, 0.97), 3), sid))

def _dept_students(dept_id, db):
    """Return enriched student dicts for a specific department."""
    rows = db.execute(
        """SELECT s.*, u.name, u.email, c.name AS course_name, c.code AS course_code,
                  sem.sem_no, dep.name AS dept_name
           FROM students s
           JOIN users u ON s.user_id = u.id
           LEFT JOIN courses c ON s.course_id = c.id
           LEFT JOIN semesters sem ON s.semester_id = sem.id
           LEFT JOIN departments dep ON s.department_id = dep.id
           WHERE s.department_id = ? AND u.role='student'
           ORDER BY u.name""", (dept_id,)).fetchall()
    result = []
    for s in rows:
        cgpa = compute_cgpa(s['id'])
        att  = get_att_pct(s['id'])
        risk = compute_dropout_risk(s['id'])
        rl, rc = risk_info(risk)
        result.append({
            'id':          s['id'],
            'user_id':     s['user_id'],
            'name':        s['name'],
            'email':       s['email'],
            'roll_no':     s['roll_no'],
            'year':        s['year'],
            'semester':    s['semester'],
            'course_name': s['course_name'] or '',
            'course_code': s['course_code'] or '',
            'department':  s['dept_name'] or '',
            'department_id': s['department_id'],
            'cgpa':        cgpa,
            'att_pct':     att,
            'attendance_pct': att,
            'risk_score':  risk,
            'risk_pct':    int(risk * 100),
            'risk_level':  rl,
            'risk_color':  rc,
        })
    return result

def _dept_faculty(dept_id, db):
    """Return faculty belonging to a department."""
    return db.execute(
        """SELECT f.*, u.name, u.email, d.name AS dept_name
           FROM faculty f
           JOIN users u ON f.user_id = u.id
           LEFT JOIN departments d ON f.department_id = d.id
           WHERE f.department_id = ?
           ORDER BY u.name""", (dept_id,)).fetchall()

def _faculty_subjects(faculty_id, db):
    """Return subjects assigned to a specific faculty member."""
    return db.execute(
        """SELECT sub.*, c.name AS course_name, sem.sem_no
           FROM subjects sub
           LEFT JOIN courses c ON sub.course_id = c.id
           LEFT JOIN semesters sem ON sub.semester_id = sem.id
           WHERE sub.faculty_id = ?
           ORDER BY sem.sem_no, sub.name""", (faculty_id,)).fetchall()

@app.context_processor
def inject_globals():
    user = None
    if 'user_id' in session:
        db = get_db()
        user = db.execute("SELECT u.*, d.name AS dept_name FROM users u LEFT JOIN departments d ON u.department_id=d.id WHERE u.id=?",
                          (session['user_id'],)).fetchone()
        db.close()
    return dict(current_user=user, session=session, current_year=datetime.now().year)

# ── PUBLIC ROUTES ─────────────────────────────────────────────────
@app.route('/')
def home():
    db = get_db()
    notices = db.execute("SELECT * FROM notices WHERE is_active=1 ORDER BY created_at DESC LIMIT 5").fetchall()
    db.close()
    return render_template('index.html', notices=notices)

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/courses')
def courses():
    db = get_db()
    all_courses = db.execute(
        """SELECT c.*, d.name AS dept_name FROM courses c
           LEFT JOIN departments d ON c.department_id = d.id
           ORDER BY c.level, c.name""").fetchall()
    db.close()
    return render_template('courses.html', courses=all_courses,
                           active_level=request.args.get('level', 'all'))

@app.route('/notices')
def notices():
    tag = request.args.get('tag', '')
    db  = get_db()
    q   = "SELECT * FROM notices WHERE is_active=1"
    if tag: q += f" AND tag='{tag}'"
    q  += " ORDER BY created_at DESC"
    rows = db.execute(q).fetchall()
    db.close()
    return render_template('notices.html', notices=rows, active_tag=tag)

@app.route('/contact', methods=['GET', 'POST'])
def contact():
    if request.method == 'POST':
        n, e, m = request.form.get('name',''), request.form.get('email',''), request.form.get('message','')
        if n and e and m:
            db = get_db()
            db.execute("INSERT INTO contact_messages(name,email,message) VALUES(?,?,?)", (n, e, m))
            db.commit(); db.close()
            return jsonify({'ok': True})
        return jsonify({'ok': False}), 400
    return render_template('contact.html')

# ── AUTH ─────────────────────────────────────────────────────────
@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        r = session.get('role')
        return redirect(url_for('student_dashboard' if r == 'student' else
                                ('faculty_dashboard' if r == 'faculty' else 'hod_dashboard')))
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        pw    = request.form.get('password', '')
        role  = request.form.get('role', '')
        db    = get_db()
        user  = db.execute(
            "SELECT u.*, d.name AS dept_name, d.id AS dept_id FROM users u LEFT JOIN departments d ON u.department_id=d.id WHERE u.email=? AND u.password=? AND u.role=?",
            (email, hash_password(pw), role)).fetchone()
        if user:
            session.permanent = bool(request.form.get('remember'))
            session.update({
                'user_id':       user['id'],
                'name':          user['name'],
                'email':         user['email'],
                'role':          user['role'],
                'department_id': user['department_id'] or '',
                'department':    user['dept_name'] or '',
            })
            if role == 'student':
                s = db.execute("SELECT id FROM students WHERE user_id=?", (user['id'],)).fetchone()
                if s: session['student_id'] = s['id']
                db.close()
                return redirect(url_for('student_dashboard'))
            elif role == 'faculty':
                f = db.execute("SELECT id FROM faculty WHERE user_id=?", (user['id'],)).fetchone()
                if f: session['faculty_id'] = f['id']
                db.close()
                return redirect(url_for('faculty_dashboard'))
            else:
                db.close()
                return redirect(url_for('hod_dashboard'))
        db.close()
        flash('Invalid credentials or role mismatch.', 'error')
    return render_template('auth/login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out successfully.', 'success')
    return redirect(url_for('login'))

@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email, np, cp = request.form.get('email',''), request.form.get('new_password',''), request.form.get('confirm_password','')
        if np != cp:
            flash('Passwords do not match.', 'error')
            return render_template('auth/forgot_password.html')
        db = get_db()
        u  = db.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()
        if u:
            db.execute("UPDATE users SET password=? WHERE email=?", (hash_password(np), email))
            db.commit(); flash('Password reset! Please login.', 'success'); db.close()
            return redirect(url_for('login'))
        flash('Email not found.', 'error'); db.close()
    return render_template('auth/forgot_password.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    db = get_db()
    depts   = db.execute("SELECT * FROM departments ORDER BY name").fetchall()
    courses = db.execute("SELECT c.*, d.name AS dept_name FROM courses c LEFT JOIN departments d ON c.department_id=d.id ORDER BY c.level,c.name").fetchall()
    db.close()

    if request.method == 'POST':
        name      = request.form.get('name','').strip()
        email     = request.form.get('email','').strip().lower()
        pw        = request.form.get('password','')
        role      = request.form.get('role','student')
        course_id = request.form.get('course_id','')
        dept_id   = request.form.get('department_id','')

        db = get_db()
        if db.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone():
            flash('Email already registered.', 'error'); db.close()
            return render_template('register.html', departments=depts, courses=courses)
        try:
            db.execute("INSERT INTO users(name,email,password,role,department_id) VALUES(?,?,?,?,?)",
                       (name, email, hash_password(pw), role, dept_id or None))
            uid = db.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()['id']

            if role == 'student' and course_id:
                course = db.execute("SELECT * FROM courses WHERE id=?", (course_id,)).fetchone()
                if course:
                    # Auto-assign semester 1 of selected course
                    sem_row = db.execute("SELECT id FROM semesters WHERE course_id=? AND sem_no=1", (course_id,)).fetchone()
                    sem_ref = sem_row['id'] if sem_row else None
                    roll = f"{course['code']}{datetime.now().year}{uid:04d}"
                    db.execute(
                        "INSERT INTO students(user_id,roll_no,course_id,department_id,semester_id,year,semester) VALUES(?,?,?,?,?,1,1)",
                        (uid, roll, course_id, course['department_id'], sem_ref))

            elif role == 'faculty':
                db.execute("INSERT INTO faculty(user_id,emp_id,department_id,designation) VALUES(?,?,?,?)",
                           (uid, f"FAC{uid:04d}", dept_id or None, 'Assistant Professor'))

            db.commit()
            flash('Registration successful! Please login.', 'success'); db.close()
            return redirect(url_for('login'))
        except Exception as e:
            flash(f'Registration error: {e}', 'error'); db.close()

    return render_template('register.html', departments=depts, courses=courses)

# ── STUDENT ROUTES ────────────────────────────────────────────────
@app.route('/student/dashboard')
@login_required('student')
def student_dashboard():
    sid = session.get('student_id')
    db  = get_db()
    student = db.execute(
        """SELECT s.*, u.name, u.email, c.name AS course_name, c.code AS course_code,
                  sem.sem_no, d.name AS dept_name
           FROM students s
           JOIN users u ON s.user_id=u.id
           LEFT JOIN courses c ON s.course_id=c.id
           LEFT JOIN semesters sem ON s.semester_id=sem.id
           LEFT JOIN departments d ON s.department_id=d.id
           WHERE s.id=?""", (sid,)).fetchone()

    raw_marks = db.execute(
        """SELECT m.*, sub.name AS subname, sub.code, sub.credits
           FROM marks m JOIN subjects sub ON m.subject_id=sub.id
           WHERE m.student_id=? ORDER BY m.semester, sub.name""", (sid,)).fetchall()

    notices = db.execute("SELECT * FROM notices WHERE is_active=1 ORDER BY created_at DESC LIMIT 3").fetchall()

    att_rows = db.execute("SELECT status FROM attendance WHERE student_id=?", (sid,)).fetchall()
    subj_att = db.execute(
        """SELECT sub.name AS subname,
                  SUM(CASE WHEN a.status='P' THEN 1 ELSE 0 END) AS present,
                  COUNT(*) AS total,
                  ROUND(SUM(CASE WHEN a.status='P' THEN 1 ELSE 0 END)*100.0/COUNT(*),1) AS pct
           FROM attendance a JOIN subjects sub ON a.subject_id=sub.id
           WHERE a.student_id=? GROUP BY sub.id""", (sid,)).fetchall()

    recalc(sid, db); db.commit(); db.close()

    ap  = sum(1 for a in att_rows if a['status'] == 'P')
    aa  = sum(1 for a in att_rows if a['status'] == 'A')
    am  = sum(1 for a in att_rows if a['status'] == 'M')
    at  = len(att_rows) or 1
    apct = round(ap / at * 100, 1)
    cgpa = compute_cgpa(sid)
    risk = compute_dropout_risk(sid)
    rl, rc = risk_info(risk)
    avg_marks = round(sum(m['total'] for m in raw_marks) / max(len(raw_marks), 1), 1)
    int_avg   = sum(m['internal1'] for m in raw_marks) / max(len(raw_marks), 1)
    pred_gpa  = round(min(10, cgpa * 0.6 + (int_avg / 20.0) * 10 * 0.4), 2)

    marks = [{'subject': m['subname'], 'semester': m['semester'], 'internal': m['internal1'],
              'external': m['external'], 'total': m['total'], 'grade': m['grade']} for m in raw_marks]
    att   = [{'subject': a['subname'], 'present': a['present'], 'total': a['total'],
              'percentage': a['pct']} for a in subj_att]

    pred      = 'Excellent' if cgpa >= 8.5 else ('Good' if cgpa >= 7 else ('Average' if cgpa >= 5 else 'Needs Improvement'))
    pred_clr  = '#00f5a0' if cgpa >= 8.5 else ('#38bdf8' if cgpa >= 7 else ('#fbbf24' if cgpa >= 5 else '#f87171'))

    return render_template('student/dashboard.html',
        student=student, marks=marks, att=att, notices=notices,
        cgpa=cgpa, risk=risk, risk_level=rl, risk_color=rc,
        att_present=ap, att_absent=aa, att_medical=am, att_total=at, att_pct=apct,
        total_subjects=len(raw_marks), avg_marks=avg_marks, avg_attendance=apct,
        pred=pred, pred_clr=pred_clr, pred_gpa=pred_gpa,
        user_name=session.get('name',''))

@app.route('/student/profile')
@login_required('student')
def student_profile():
    sid = session.get('student_id'); db = get_db()
    student = db.execute(
        """SELECT s.*, u.name, u.email, c.name AS course_name, d.name AS dept_name, sem.sem_no
           FROM students s JOIN users u ON s.user_id=u.id
           LEFT JOIN courses c ON s.course_id=c.id
           LEFT JOIN departments d ON s.department_id=d.id
           LEFT JOIN semesters sem ON s.semester_id=sem.id
           WHERE s.id=?""", (sid,)).fetchone()
    cert = db.execute("SELECT * FROM certificates WHERE student_id=? LIMIT 1", (sid,)).fetchone()
    db.close()
    cgpa = compute_cgpa(sid); att = get_att_pct(sid); risk = compute_dropout_risk(sid)
    rl, rc = risk_info(risk)
    return render_template('student/profile.html', student=student, cert=cert,
                           cgpa=cgpa, att_pct=att, risk=risk, risk_level=rl, risk_color=rc,
                           user_name=session.get('name',''))

@app.route('/student/results')
@login_required('student')
def student_results():
    sid = session.get('student_id'); db = get_db()
    marks = db.execute(
        """SELECT m.*, sub.name AS subname, sub.code, sub.credits, sem.sem_no
           FROM marks m JOIN subjects sub ON m.subject_id=sub.id
           LEFT JOIN semesters sem ON sub.semester_id=sem.id
           WHERE m.student_id=? ORDER BY sem.sem_no, sub.name""", (sid,)).fetchall()
    db.close()
    cgpa = compute_cgpa(sid)
    return render_template('student/results.html', marks=marks, cgpa=cgpa,
                           user_name=session.get('name',''))

@app.route('/student/attendance')
@login_required('student')
def student_attendance():
    sid = session.get('student_id'); db = get_db()
    subj_att = [dict(r) for r in db.execute(
        """SELECT sub.name AS subname, sub.code,
                  SUM(CASE WHEN a.status='P' THEN 1 ELSE 0 END) AS present,
                  SUM(CASE WHEN a.status='A' THEN 1 ELSE 0 END) AS absent,
                  SUM(CASE WHEN a.status='M' THEN 1 ELSE 0 END) AS medical,
                  COUNT(*) AS total,
                  ROUND(SUM(CASE WHEN a.status='P' THEN 1 ELSE 0 END)*100.0/COUNT(*),1) AS pct
           FROM attendance a JOIN subjects sub ON a.subject_id=sub.id
           WHERE a.student_id=? GROUP BY sub.id ORDER BY sub.name""", (sid,)).fetchall()]
    db.close()
    overall = get_att_pct(sid)
    return render_template('student/attendance.html', subj_att=subj_att, overall=overall,
                           avg_attendance=overall,
                           user_name=session.get('name',''))

@app.route('/student/edit-profile', methods=['GET', 'POST'])
@login_required('student')
def student_edit_profile():
    sid = session.get('student_id'); uid = session['user_id']
    if request.method == 'POST':
        action = request.form.get('action', 'profile')
        db = get_db()
        if action == 'password':
            old_pw  = request.form.get('old_password','')
            new_pw  = request.form.get('new_password','')
            confirm = request.form.get('confirm_password','')
            user = db.execute("SELECT password FROM users WHERE id=?", (uid,)).fetchone()
            if not user or user['password'] != hash_password(old_pw):
                flash('Current password is incorrect.', 'error')
            elif new_pw != confirm:
                flash('New passwords do not match.', 'error')
            elif len(new_pw) < 6:
                flash('Password must be at least 6 characters.', 'error')
            else:
                db.execute("UPDATE users SET password=? WHERE id=?", (hash_password(new_pw), uid))
                db.commit(); flash('Password updated successfully!', 'success')
        else:
            name = request.form.get('name','').strip() or session.get('name','')
            db.execute("UPDATE users SET name=? WHERE id=?", (name, uid))
            if sid:
                db.execute("UPDATE students SET phone=?,address=?,dob=? WHERE id=?",
                           (request.form.get('phone',''), request.form.get('address',''),
                            request.form.get('dob',''), sid))
            db.commit(); session['name'] = name
            flash('Profile updated successfully!', 'success')
        db.close()
        return redirect(url_for('student_edit_profile'))
    db = get_db()
    student = db.execute(
        """SELECT s.*, u.name, u.email, c.name AS course_name, d.name AS dept_name
           FROM students s JOIN users u ON s.user_id=u.id
           LEFT JOIN courses c ON s.course_id=c.id
           LEFT JOIN departments d ON s.department_id=d.id
           WHERE s.id=?""", (sid,)).fetchone() if sid else None
    db.close()
    return render_template('student/edit_profile.html', student=student,
                           user_name=session.get('name',''), user_email=session.get('email',''))

@app.route('/student/ai-insights')
@login_required('student')
def student_ai_insights():
    sid  = session.get('student_id')
    cgpa = compute_cgpa(sid); risk = compute_dropout_risk(sid); att = get_att_pct(sid)
    rl, rc = risk_info(risk)
    db   = get_db()
    marks = db.execute("SELECT sub.name, m.total FROM marks m JOIN subjects sub ON m.subject_id=sub.id WHERE m.student_id=?", (sid,)).fetchall()
    db.close()
    weak = [m for m in marks if m['total'] < 60]
    avg_marks = round(sum(m['total'] for m in marks) / max(len(marks),1), 1)
    return render_template('student/ai_insights.html', cgpa=cgpa, risk=risk,
                           risk_level=rl, risk_color=rc, att_pct=att, weak_subjects=weak,
                           avg_marks=avg_marks, avg_attendance=att,
                           user_name=session.get('name',''))

@app.route('/student/chatbot')
@login_required('student')
def student_chatbot():
    return render_template('student/chatbot.html', user_name=session.get('name',''))

@app.route('/student/chatbot/api', methods=['POST'])
@login_required('student')
def chatbot_api():
    sid = session.get('student_id')
    msg = request.json.get('message','').strip().lower()
    db  = get_db()
    marks    = db.execute("SELECT m.*, sub.name AS subject FROM marks m JOIN subjects sub ON m.subject_id=sub.id WHERE m.student_id=?", (sid,)).fetchall()
    att_rows = db.execute(
        """SELECT sub.name AS subject,
                  SUM(CASE WHEN a.status='P' THEN 1 ELSE 0 END) AS present,
                  COUNT(*) AS total,
                  ROUND(SUM(CASE WHEN a.status='P' THEN 1 ELSE 0 END)*100.0/COUNT(*),1) AS pct
           FROM attendance a JOIN subjects sub ON a.subject_id=sub.id
           WHERE a.student_id=? GROUP BY sub.id""", (sid,)).fetchall()
    notices = db.execute("SELECT title FROM notices WHERE is_active=1 ORDER BY created_at DESC LIMIT 3").fetchall()
    db.close()
    cgpa = compute_cgpa(sid); risk = compute_dropout_risk(sid)
    rl, _ = risk_info(risk); att_pct = get_att_pct(sid)
    avg_marks = round(sum(m['total'] for m in marks) / max(len(marks),1), 1)

    reply = ""
    if any(w in msg for w in ['mark','result','score','grade','subject']):
        if marks:
            lines = [f"<b>{m['subject']}</b>: {m['total']}/100 ({m['grade']})" for m in marks]
            reply = f"📊 Your marks:<br>{'<br>'.join(lines)}<br><br>Average: <b>{avg_marks}%</b>"
        else:
            reply = "No marks uploaded yet. Contact your faculty."
    elif any(w in msg for w in ['attendance','present','absent','bunk']):
        if att_rows:
            lines  = [f"<b>{a['subject']}</b>: {a['pct']}% ({a['present']}/{a['total']})" for a in att_rows]
            status = "✅ Safe" if att_pct >= 75 else "⚠️ Below 75% — Risk of detention!"
            reply  = f"📅 Attendance ({status}):<br>{'<br>'.join(lines)}<br><br>Overall: <b>{att_pct}%</b>"
        else:
            reply = "No attendance records found yet."
    elif any(w in msg for w in ['cgpa','gpa','pointer','performance']):
        reply = f"🎯 Your CGPA: <b>{cgpa}</b>/10 | Avg Marks: <b>{avg_marks}%</b> | AI Risk: <b>{rl}</b>"
    elif any(w in msg for w in ['risk','dropout','predict','ai']):
        reply = f"🤖 Dropout Risk: <b>{int(risk*100)}% ({rl})</b> | CGPA: <b>{cgpa}</b> | Att: <b>{att_pct}%</b>"
    elif any(w in msg for w in ['exam','schedule','timetable']):
        reply = "📅 Exam info is on the Notices board. <a href='/notices'>View Notices →</a>"
    elif any(w in msg for w in ['hello','hi','hey']):
        reply = f"👋 Hello <b>{session.get('name','Student')}</b>! Ask me about marks, attendance, CGPA, or AI predictions."
    else:
        reply = "🤖 I can help with: marks, attendance, CGPA, AI dropout risk, exam schedules."
    return jsonify({'reply': reply})

# ── FACULTY ROUTES ────────────────────────────────────────────────
@app.route('/faculty/dashboard')
@login_required('faculty')
def faculty_dashboard():
    dept_id = session.get('department_id')
    fac_id  = session.get('faculty_id')
    db      = get_db()

    # Faculty sees only students in their department
    students = _dept_students(dept_id, db)
    # Faculty sees only their assigned subjects
    subjects = _faculty_subjects(fac_id, db)
    notices  = db.execute("SELECT * FROM notices WHERE is_active=1 ORDER BY created_at DESC LIMIT 3").fetchall()
    db.close()

    dept_stats = {
        'total_students': len(students),
        'avg_cgpa':       round(sum(s['cgpa'] for s in students) / max(len(students),1), 2),
        'at_risk':        sum(1 for s in students if s['risk_score'] >= 0.45),
        'avg_attendance': round(sum(s['att_pct'] for s in students) / max(len(students),1), 1),
    }
    return render_template('faculty/dashboard.html',
                           students=students, subjects=subjects,
                           notices=notices, dept_stats=dept_stats)

@app.route('/faculty/upload-marks', methods=['GET', 'POST'])
@login_required('faculty')
def upload_marks():
    dept_id = session.get('department_id')
    fac_id  = session.get('faculty_id')
    db      = get_db()
    students = _dept_students(dept_id, db)
    # Faculty can only upload marks for subjects they are assigned to
    subjects = _faculty_subjects(fac_id, db)

    if request.method == 'POST':
        sf    = int(request.form.get('student_id', 0))
        subj  = int(request.form.get('subject_id', 0))
        sem   = int(request.form.get('semester', 1))
        i1    = float(request.form.get('internal1', 0))
        i2    = float(request.form.get('internal2', 0))
        ext   = float(request.form.get('external', 0))
        total = round(i1 + i2 + ext, 1)
        grade = get_grade(total)
        try:
            db.execute(
                """INSERT INTO marks(student_id,subject_id,semester,internal1,internal2,external,total,grade)
                   VALUES(?,?,?,?,?,?,?,?)
                   ON CONFLICT(student_id,subject_id,semester)
                   DO UPDATE SET internal1=?,internal2=?,external=?,total=?,grade=?,uploaded_at=CURRENT_TIMESTAMP""",
                (sf, subj, sem, i1, i2, ext, total, grade, i1, i2, ext, total, grade))
            recalc(sf, db); db.commit()
            flash(f'Marks uploaded! Total: {total} | Grade: {grade}', 'success')
        except Exception as e:
            flash(f'Error: {e}', 'error')
        db.close()
        return redirect(url_for('upload_marks'))

    recent = db.execute(
        """SELECT m.*, sub.name AS subname, u.name AS stuname
           FROM marks m JOIN subjects sub ON m.subject_id=sub.id
           JOIN students s ON m.student_id=s.id JOIN users u ON s.user_id=u.id
           WHERE s.department_id=?
           ORDER BY m.uploaded_at DESC LIMIT 10""", (dept_id,)).fetchall()
    db.close()
    return render_template('faculty/upload_marks.html',
                           students=students, subjects=subjects, recent_marks=recent)

@app.route('/faculty/attendance', methods=['GET', 'POST'])
@login_required('faculty')
def manage_attendance():
    dept_id = session.get('department_id')
    fac_id  = session.get('faculty_id')
    db      = get_db()
    students = _dept_students(dept_id, db)
    subjects = _faculty_subjects(fac_id, db)

    if request.method == 'POST':
        subj     = request.form.get('subject_id')
        att_date = request.form.get('date', str(date.today()))
        for st in students:
            status = request.form.get(f'status_{st["id"]}', 'A')
            try:
                db.execute(
                    """INSERT INTO attendance(student_id,subject_id,date,status) VALUES(?,?,?,?)
                       ON CONFLICT(student_id,subject_id,date) DO UPDATE SET status=?""",
                    (st['id'], subj, att_date, status, status))
            except: pass
        for st in students: recalc(st['id'], db)
        db.commit()
        flash(f'Attendance saved for {att_date}!', 'success')
        db.close()
        return redirect(url_for('manage_attendance'))
    db.close()
    return render_template('faculty/attendance.html',
                           students=students, subjects=subjects, today=str(date.today()))

@app.route('/faculty/weak-students')
@login_required('faculty')
def weak_students():
    threshold = float(request.args.get('threshold', 0.45))
    dept_id   = session.get('department_id')
    db        = get_db()
    students  = _dept_students(dept_id, db)
    db.close()
    weak = [s for s in students if s['risk_score'] >= threshold]
    weak.sort(key=lambda x: x['risk_score'], reverse=True)
    return render_template('faculty/weak_students.html', students=weak, threshold=threshold)

@app.route('/faculty/class-analytics')
@login_required('faculty')
def class_analytics():
    dept_id  = session.get('department_id')
    db       = get_db()
    students = _dept_students(dept_id, db)
    db.close()
    cgpa_b = {'0–4':0,'4–6':0,'6–7':0,'7–8':0,'8–9':0,'9–10':0}
    att_b  = {'<60%':0,'60–75%':0,'75–85%':0,'85–95%':0,'95%+':0}
    low = med = high = 0
    for st in students:
        c_ = st['cgpa']; a = st['att_pct']; r = st['risk_score']
        if   c_ < 4:  cgpa_b['0–4']  += 1
        elif c_ < 6:  cgpa_b['4–6']  += 1
        elif c_ < 7:  cgpa_b['6–7']  += 1
        elif c_ < 8:  cgpa_b['7–8']  += 1
        elif c_ < 9:  cgpa_b['8–9']  += 1
        else:         cgpa_b['9–10'] += 1
        if   a < 60:  att_b['<60%']    += 1
        elif a < 75:  att_b['60–75%']  += 1
        elif a < 85:  att_b['75–85%']  += 1
        elif a < 95:  att_b['85–95%']  += 1
        else:         att_b['95%+']    += 1
        if   r >= 0.55: high += 1
        elif r >= 0.25: med  += 1
        else:           low  += 1
    ranked = sorted(students, key=lambda x: x['cgpa'], reverse=True)
    n = max(len(ranked), 1)
    return render_template('faculty/class_analytics.html',
        dept_stats={'total_students': len(students),
                    'avg_cgpa': round(sum(s['cgpa'] for s in students) / n, 2),
                    'at_risk': high + med,
                    'avg_attendance': round(sum(s['att_pct'] for s in students) / n, 1)},
        cgpa_labels=json.dumps(list(cgpa_b.keys())),
        cgpa_data=json.dumps(list(cgpa_b.values())),
        att_labels=json.dumps(list(att_b.keys())),
        att_data=json.dumps(list(att_b.values())),
        risk_labels=json.dumps(['Low','Medium','High']),
        risk_vals=json.dumps([low, med, high]),
        risk_breakdown=[('Low Risk',low,'#00f5a0'),('Medium Risk',med,'#fbbf24'),('High Risk',high,'#f87171')],
        students_ranked=ranked)

# ── HOD ROUTES ───────────────────────────────────────────────────
@app.route('/hod/dashboard')
@login_required('hod')
def hod_dashboard():
    dept_id = session.get('department_id')
    db      = get_db()

    # HOD sees ONLY their department's data
    students = _dept_students(dept_id, db)
    faculty  = _dept_faculty(dept_id, db)
    notices  = db.execute("SELECT * FROM notices ORDER BY created_at DESC LIMIT 5").fetchall()
    um       = db.execute("SELECT COUNT(*) AS c FROM contact_messages").fetchone()['c']
    dept     = db.execute("SELECT * FROM departments WHERE id=?", (dept_id,)).fetchone()
    db.close()

    students.sort(key=lambda x: x['risk_score'], reverse=True)
    n      = max(len(students), 1)
    avg_c  = round(sum(s['cgpa'] for s in students) / n, 2)
    avg_a  = round(sum(s['att_pct'] for s in students) / n, 1)
    at_risk = sum(1 for s in students if s['risk_score'] >= 0.45)

    return render_template('hod/dashboard.html',
        dept=dept,
        total_students=len(students),
        total_faculty=len(faculty),
        avg_cgpa=avg_c, avg_att=avg_a, at_risk=at_risk,
        students=students[:8], faculty=faculty[:6],
        notices=notices, unread_messages=um,
        stats={'total_students': len(students), 'avg_cgpa': avg_c,
               'at_risk': at_risk, 'avg_attendance': avg_a})

@app.route('/hod/students', methods=['GET', 'POST'])
@login_required('hod')
def hod_students():
    dept_id = session.get('department_id')
    search  = request.args.get('q','').strip()
    db      = get_db()

    if request.method == 'POST' and request.form.get('action') == 'add':
        name      = request.form.get('name','').strip()
        email     = request.form.get('email','').strip().lower()
        course_id = request.form.get('course_id','')
        roll_no   = request.form.get('roll_no','').strip()
        try:
            db.execute("INSERT INTO users(name,email,password,role,department_id) VALUES(?,?,?,?,?)",
                       (name, email, hash_password('student123'), 'student', dept_id))
            uid = db.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()['id']
            if course_id:
                course = db.execute("SELECT * FROM courses WHERE id=? AND department_id=?", (course_id, dept_id)).fetchone()
                if course:
                    sem_row = db.execute("SELECT id FROM semesters WHERE course_id=? AND sem_no=1", (course_id,)).fetchone()
                    db.execute(
                        "INSERT INTO students(user_id,roll_no,course_id,department_id,semester_id,year,semester) VALUES(?,?,?,?,?,1,1)",
                        (uid, roll_no or f"{course['code']}{datetime.now().year}{uid:04d}",
                         course_id, dept_id, sem_row['id'] if sem_row else None))
            db.commit()
            flash(f'Student {name} added! Default password: student123', 'success')
        except Exception as e:
            flash(f'Error: {e}', 'error')
        db.close()
        return redirect(url_for('hod_students'))

    # Show only department students
    students = _dept_students(dept_id, db)
    if search:
        students = [s for s in students if search.lower() in s['name'].lower() or search.lower() in s['roll_no'].lower()]

    # Courses available in this department (for Add Student form)
    courses = db.execute("SELECT * FROM courses WHERE department_id=?", (dept_id,)).fetchall()
    db.close()
    return render_template('hod/students.html', students=students, search=search, courses=courses)

@app.route('/hod/students/delete/<int:sid>', methods=['POST'])
@login_required('hod')
def hod_delete_student(sid):
    dept_id = session.get('department_id')
    db = get_db()
    # Safety: ensure student belongs to HOD's dept
    stu = db.execute("SELECT department_id FROM students WHERE id=?", (sid,)).fetchone()
    if stu and stu['department_id'] == dept_id:
        uid = db.execute("SELECT user_id FROM students WHERE id=?", (sid,)).fetchone()['user_id']
        db.execute("DELETE FROM users WHERE id=?", (uid,))
        db.commit()
        flash('Student deleted.', 'success')
    else:
        flash('Access denied.', 'error')
    db.close()
    return redirect(url_for('hod_students'))

@app.route('/hod/faculty', methods=['GET', 'POST'])
@login_required('hod')
def hod_faculty():
    dept_id = session.get('department_id')
    db      = get_db()

    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'add':
            name  = request.form.get('name','').strip()
            email = request.form.get('email','').strip().lower()
            emp   = request.form.get('emp_id','').strip()
            desig = request.form.get('designation','Assistant Professor')
            try:
                db.execute("INSERT INTO users(name,email,password,role,department_id) VALUES(?,?,?,?,?)",
                           (name, email, hash_password('faculty123'), 'faculty', dept_id))
                uid = db.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()['id']
                db.execute("INSERT INTO faculty(user_id,emp_id,department_id,designation) VALUES(?,?,?,?)",
                           (uid, emp or f"FAC{uid:04d}", dept_id, desig))
                db.commit()
                flash(f'Faculty {name} added! Default password: faculty123', 'success')
            except Exception as e:
                flash(f'Error: {e}', 'error')
        elif action == 'edit':
            db.execute("UPDATE faculty SET designation=? WHERE id=? AND department_id=?",
                       (request.form.get('designation',''), request.form.get('faculty_id'), dept_id))
            db.commit(); flash('Faculty updated!', 'success')
        db.close()
        return redirect(url_for('hod_faculty'))

    faculty = _dept_faculty(dept_id, db)
    db.close()
    return render_template('hod/faculty.html', faculty=faculty)

@app.route('/hod/faculty/delete/<int:fid>', methods=['POST'])
@login_required('hod')
def hod_delete_faculty(fid):
    dept_id = session.get('department_id')
    db = get_db()
    fac = db.execute("SELECT department_id, user_id FROM faculty WHERE id=?", (fid,)).fetchone()
    if fac and fac['department_id'] == dept_id:
        db.execute("DELETE FROM users WHERE id=?", (fac['user_id'],))
        db.commit(); flash('Faculty deleted.', 'success')
    else:
        flash('Access denied.', 'error')
    db.close()
    return redirect(url_for('hod_faculty'))

@app.route('/hod/notices', methods=['GET', 'POST'])
@login_required('hod')
def hod_notices():
    db = get_db()
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'add':
            db.execute("INSERT INTO notices(title,body,tag,color,created_by) VALUES(?,?,?,?,?)",
                       (request.form.get('title','').strip(), request.form.get('body','').strip(),
                        request.form.get('tag','INFO').upper(), request.form.get('color','primary'),
                        session['user_id']))
            db.commit(); flash('Notice posted!', 'success')
        elif action == 'delete':
            db.execute("UPDATE notices SET is_active=0 WHERE id=?", (request.form.get('notice_id'),))
            db.commit(); flash('Notice removed.', 'success')
        db.close()
        return redirect(url_for('hod_notices'))
    notices = db.execute("SELECT * FROM notices ORDER BY created_at DESC").fetchall()
    db.close()
    return render_template('hod/notices.html', notices=notices)

@app.route('/hod/dept-analytics')
@login_required('hod')
def dept_analytics():
    dept_id  = session.get('department_id')
    db       = get_db()
    students = _dept_students(dept_id, db)
    all_marks = db.execute(
        """SELECT m.grade FROM marks m JOIN students s ON m.student_id=s.id
           WHERE s.department_id=?""", (dept_id,)).fetchall()
    courses = db.execute("SELECT * FROM courses WHERE department_id=?", (dept_id,)).fetchall()
    db.close()

    cgpas = [s['cgpa'] for s in students]
    atts  = [s['att_pct'] for s in students]
    risks = [s['risk_score'] for s in students]
    n     = max(len(students), 1)
    gd    = {'O':0,'A+':0,'A':0,'B':0,'C':0,'F':0}
    for m in all_marks:
        if m['grade'] in gd: gd[m['grade']] += 1

    cluster_data = [
        ('🏆','High Achiever',    sum(1 for c_,a in zip(cgpas,atts) if c_>=8 and a>=85), '#00f5a0'),
        ('📈','Average Performer',sum(1 for c_ in cgpas if 6.5<=c_<8),                  '#38bdf8'),
        ('⚠️','Needs Improvement',sum(1 for c_ in cgpas if 5<=c_<6.5),                  '#fbbf24'),
        ('🚨','At Risk',          sum(1 for c_ in cgpas if c_<5),                        '#f87171'),
    ]
    course_stats = [{'name': co['name'], 'seats': 60,
                     'enrolled': sum(1 for s in students if s['course_code'] == co['code'])}
                    for co in courses]

    return render_template('hod/dept_analytics.html',
        stats={'total_students': n, 'avg_cgpa': round(sum(cgpas)/n,2),
               'at_risk': sum(1 for r in risks if r>=0.45),
               'avg_attendance': round(sum(atts)/n,1)},
        grade_dist=json.dumps([gd['O'],gd['A+'],gd['A'],gd['B'],gd['C'],gd['F']]),
        cluster_data=cluster_data, courses=course_stats)

@app.route('/hod/messages')
@login_required('hod')
def hod_messages():
    db   = get_db()
    msgs = db.execute("SELECT * FROM contact_messages ORDER BY created_at DESC").fetchall()
    db.close()
    return render_template('hod/messages.html', messages=msgs)

@app.route('/hod/reports')
@login_required('hod')
def hod_reports():
    dept_id = session.get('department_id')
    db      = get_db()
    dept    = db.execute("SELECT * FROM departments WHERE id=?", (dept_id,)).fetchone()
    db.close()
    return render_template('hod/reports.html', dept=dept)

@app.route('/hod/reports/download')
@login_required('hod')
def download_report():
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib import colors
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, HRFlowable
        from reportlab.lib.units import cm
        from reportlab.lib.enums import TA_CENTER
        import datetime as dt

        dept_id   = session.get('department_id')
        rtype     = request.args.get('type','dept')
        db        = get_db()
        dept      = db.execute("SELECT * FROM departments WHERE id=?", (dept_id,)).fetchone()
        students  = _dept_students(dept_id, db)
        db.close()

        buf = io.BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=1.8*cm, rightMargin=1.8*cm,
                                topMargin=2*cm, bottomMargin=2*cm)
        styles   = getSampleStyleSheet()
        DARK     = colors.HexColor('#04080f'); GREEN  = colors.HexColor('#00f5a0')
        GRAY     = colors.HexColor('#64748b'); LGRAY  = colors.HexColor('#f1f5f9')
        title_s  = ParagraphStyle('T', fontSize=18, textColor=DARK, spaceAfter=4,
                                  fontName='Helvetica-Bold', alignment=TA_CENTER)
        sub_s    = ParagraphStyle('S', fontSize=9,  textColor=GRAY, spaceAfter=12,
                                  fontName='Helvetica', alignment=TA_CENTER)
        head_s   = ParagraphStyle('H', fontSize=13, textColor=DARK, spaceBefore=14,
                                  spaceAfter=6, fontName='Helvetica-Bold')
        tbl_style = TableStyle([
            ('BACKGROUND', (0,0),(-1,0), DARK), ('TEXTCOLOR', (0,0),(-1,0), GREEN),
            ('FONTNAME',   (0,0),(-1,0), 'Helvetica-Bold'), ('FONTSIZE', (0,0),(-1,0), 9),
            ('ALIGN',      (0,0),(-1,-1),'CENTER'),
            ('ROWBACKGROUNDS',(0,1),(-1,-1),[LGRAY, colors.white]),
            ('FONTSIZE',   (0,1),(-1,-1), 8), ('FONTNAME', (0,1),(-1,-1), 'Helvetica'),
            ('GRID',       (0,0),(-1,-1), 0.4, colors.HexColor('#e2e8f0')),
            ('TOPPADDING', (0,0),(-1,-1), 5), ('BOTTOMPADDING',(0,0),(-1,-1), 5),
        ])
        story = [
            Paragraph(f'College Academic Management System', title_s),
            Paragraph(f'Department: {dept["name"] if dept else ""} | Generated: {dt.datetime.now().strftime("%d %B %Y")} | By: {session.get("name","HOD")}', sub_s),
            HRFlowable(width='100%', thickness=2, color=GREEN, spaceAfter=16),
        ]
        if rtype in ('dept','risk'):
            story.append(Paragraph('📊 Student Performance Report' if rtype == 'dept' else '🚨 At-Risk Students', head_s))
            story.append(Spacer(1, 8))
            data = [['#','Name','Roll No','Course','Sem','CGPA','Att%','Risk%']]
            rows_to_show = students if rtype == 'dept' else [s for s in students if s['risk_score'] >= 0.35]
            rows_to_show = sorted(rows_to_show, key=lambda x: x['risk_score'], reverse=(rtype=='risk'))
            for i, s in enumerate(rows_to_show, 1):
                data.append([str(i), s['name'], s['roll_no'], s['course_code'],
                              str(s['semester']), str(s['cgpa']),
                              f"{s['att_pct']}%", f"{s['risk_pct']}%"])
            if len(data) == 1: data.append(['—','No records found','','','','','',''])
            t = Table(data, colWidths=[0.6*cm,4*cm,2.8*cm,1.8*cm,1*cm,1.4*cm,1.4*cm,1.4*cm], repeatRows=1)
            t.setStyle(tbl_style); story.append(t)
        elif rtype == 'attendance':
            story.append(Paragraph('📅 Attendance Summary', head_s)); story.append(Spacer(1,8))
            data = [['#','Name','Roll No','Att%','Status']]
            for i,s in enumerate(students, 1):
                status = 'Good' if s['att_pct']>=75 else ('Warning' if s['att_pct']>=60 else 'Critical')
                data.append([str(i), s['name'], s['roll_no'], f"{s['att_pct']}%", status])
            t = Table(data, colWidths=[0.6*cm,5*cm,3*cm,2*cm,2*cm], repeatRows=1)
            t.setStyle(tbl_style); story.append(t)

        story.append(Spacer(1,20))
        story.append(HRFlowable(width='100%', thickness=1, color=GRAY))
        story.append(Paragraph('College Academic Management System © 2026 · Confidential', sub_s))
        doc.build(story); buf.seek(0)
        fname = {'dept':'dept_performance','risk':'at_risk','attendance':'attendance_summary'}.get(rtype,'report')
        return send_file(buf, mimetype='application/pdf', as_attachment=True,
                         download_name=f'{fname}_{dt.datetime.now().strftime("%Y%m%d")}.pdf')
    except Exception as e:
        flash(f'Report error: {e}', 'error')
        return redirect(url_for('hod_reports'))

# ── API ───────────────────────────────────────────────────────────
@app.route('/api/student/marks/<int:sid>')
def api_marks(sid):
    db = get_db()
    marks = db.execute("SELECT sub.name, m.total FROM marks m JOIN subjects sub ON m.subject_id=sub.id WHERE m.student_id=?", (sid,)).fetchall()
    db.close()
    return jsonify([dict(r) for r in marks])

@app.route('/api/notices')
def api_notices():
    db = get_db()
    notices = db.execute("SELECT * FROM notices WHERE is_active=1 ORDER BY created_at DESC LIMIT 10").fetchall()
    db.close()
    return jsonify([dict(r) for r in notices])

if __name__ == '__main__':
    if not os.path.exists(DB_PATH):
        init_db()
        print("✅ Database initialized!")
    app.run(debug=True, port=5000, host='0.0.0.0')
