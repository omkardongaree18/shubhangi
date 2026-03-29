import sqlite3, os, hashlib, random
from datetime import date, timedelta

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'university.db')

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def hash_password(pwd):
    return hashlib.sha256(pwd.encode()).hexdigest()

def init_db():
    conn = get_db()
    c = conn.cursor()
    c.executescript("""
    -- ── DEPARTMENTS ─────────────────────────────────────────────
    CREATE TABLE IF NOT EXISTS departments (
        id   INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL,
        code TEXT UNIQUE NOT NULL
    );

    -- ── COURSES (B.Com, B.Sc, M.Com, MCA) ──────────────────────
    CREATE TABLE IF NOT EXISTS courses (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        name          TEXT NOT NULL,
        code          TEXT UNIQUE NOT NULL,
        department_id INTEGER REFERENCES departments(id) ON DELETE CASCADE,
        duration_years INTEGER DEFAULT 3,
        total_semesters INTEGER DEFAULT 6,
        level         TEXT DEFAULT 'UG'   -- UG / PG
    );

    -- ── SEMESTERS ────────────────────────────────────────────────
    CREATE TABLE IF NOT EXISTS semesters (
        id        INTEGER PRIMARY KEY AUTOINCREMENT,
        course_id INTEGER REFERENCES courses(id) ON DELETE CASCADE,
        sem_no    INTEGER NOT NULL,
        UNIQUE(course_id, sem_no)
    );

    -- ── SUBJECTS (mapped to course + semester) ───────────────────
    CREATE TABLE IF NOT EXISTS subjects (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        name        TEXT NOT NULL,
        code        TEXT UNIQUE NOT NULL,
        course_id   INTEGER REFERENCES courses(id) ON DELETE CASCADE,
        semester_id INTEGER REFERENCES semesters(id) ON DELETE CASCADE,
        department_id INTEGER REFERENCES departments(id) ON DELETE CASCADE,
        credits     INTEGER DEFAULT 4,
        faculty_id  INTEGER  -- assigned faculty (references faculty.id)
    );

    -- ── USERS ────────────────────────────────────────────────────
    CREATE TABLE IF NOT EXISTS users (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        name       TEXT NOT NULL,
        email      TEXT UNIQUE NOT NULL,
        password   TEXT NOT NULL,
        role       TEXT NOT NULL CHECK(role IN ('student','faculty','hod')),
        department_id INTEGER REFERENCES departments(id),
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    -- ── STUDENTS ─────────────────────────────────────────────────
    CREATE TABLE IF NOT EXISTS students (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id       INTEGER UNIQUE REFERENCES users(id) ON DELETE CASCADE,
        roll_no       TEXT UNIQUE NOT NULL,
        course_id     INTEGER REFERENCES courses(id),
        department_id INTEGER REFERENCES departments(id),
        semester_id   INTEGER REFERENCES semesters(id),
        year          INTEGER DEFAULT 1,
        semester      INTEGER DEFAULT 1,
        cgpa          REAL DEFAULT 0.0,
        dropout_risk  REAL DEFAULT 0.0,
        phone         TEXT,
        address       TEXT,
        dob           TEXT
    );

    -- ── FACULTY ──────────────────────────────────────────────────
    CREATE TABLE IF NOT EXISTS faculty (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id       INTEGER UNIQUE REFERENCES users(id) ON DELETE CASCADE,
        emp_id        TEXT UNIQUE NOT NULL,
        department_id INTEGER REFERENCES departments(id),
        designation   TEXT DEFAULT 'Assistant Professor',
        phone         TEXT
    );

    -- ── MARKS ────────────────────────────────────────────────────
    CREATE TABLE IF NOT EXISTS marks (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id  INTEGER REFERENCES students(id) ON DELETE CASCADE,
        subject_id  INTEGER REFERENCES subjects(id) ON DELETE CASCADE,
        semester    INTEGER,
        internal1   REAL DEFAULT 0,
        internal2   REAL DEFAULT 0,
        external    REAL DEFAULT 0,
        total       REAL DEFAULT 0,
        grade       TEXT DEFAULT 'F',
        uploaded_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(student_id, subject_id, semester)
    );

    -- ── ATTENDANCE ───────────────────────────────────────────────
    CREATE TABLE IF NOT EXISTS attendance (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id INTEGER REFERENCES students(id) ON DELETE CASCADE,
        subject_id INTEGER REFERENCES subjects(id) ON DELETE CASCADE,
        date       TEXT NOT NULL,
        status     TEXT CHECK(status IN ('P','A','M')) DEFAULT 'P',
        UNIQUE(student_id, subject_id, date)
    );

    -- ── NOTICES ──────────────────────────────────────────────────
    CREATE TABLE IF NOT EXISTS notices (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        title      TEXT NOT NULL,
        body       TEXT NOT NULL,
        tag        TEXT DEFAULT 'INFO',
        color      TEXT DEFAULT 'primary',
        created_by INTEGER,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        is_active  INTEGER DEFAULT 1
    );

    -- ── CONTACT MESSAGES ─────────────────────────────────────────
    CREATE TABLE IF NOT EXISTS contact_messages (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        name       TEXT, email TEXT, message TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    -- ── CERTIFICATES ─────────────────────────────────────────────
    CREATE TABLE IF NOT EXISTS certificates (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id INTEGER REFERENCES students(id),
        title      TEXT,
        eth_hash   TEXT,
        tx_id      TEXT,
        issued_at  DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    """)
    conn.commit()

    # ── SEED DEPARTMENTS ──────────────────────────────────────────
    depts = [
        ('Commerce', 'COM'),
        ('Science',  'SCI'),
        ('Computer Applications', 'MCA'),
    ]
    for name, code in depts:
        try: c.execute("INSERT INTO departments (name,code) VALUES (?,?)", (name, code))
        except: pass
    conn.commit()

    def dept_id(code):
        return c.execute("SELECT id FROM departments WHERE code=?", (code,)).fetchone()['id']

    # ── SEED COURSES ──────────────────────────────────────────────
    courses = [
        ('B.Com', 'BCOM', dept_id('COM'), 3, 6, 'UG'),
        ('B.Sc',  'BSC',  dept_id('SCI'), 3, 6, 'UG'),
        ('M.Com', 'MCOM', dept_id('COM'), 2, 4, 'PG'),
        ('MCA',   'MCA',  dept_id('MCA'), 2, 4, 'PG'),
    ]
    for row in courses:
        try: c.execute("INSERT INTO courses (name,code,department_id,duration_years,total_semesters,level) VALUES (?,?,?,?,?,?)", row)
        except: pass
    conn.commit()

    def course_id(code):
        return c.execute("SELECT id FROM courses WHERE code=?", (code,)).fetchone()['id']

    # ── SEED SEMESTERS ────────────────────────────────────────────
    for ccode, n_sems in [('BCOM',6),('BSC',6),('MCOM',4),('MCA',4)]:
        cid = course_id(ccode)
        for s in range(1, n_sems+1):
            try: c.execute("INSERT INTO semesters (course_id,sem_no) VALUES (?,?)", (cid, s))
            except: pass
    conn.commit()

    def sem_id(ccode, sem_no):
        cid = course_id(ccode)
        return c.execute("SELECT id FROM semesters WHERE course_id=? AND sem_no=?", (cid, sem_no)).fetchone()['id']

    # ── SEED SUBJECTS (department + course + semester mapped) ──────
    # B.Com Subjects (6 semesters)
    bcom_subjects = {
        1: [('Financial Accounting I',    'BCOM101'), ('Business Mathematics',     'BCOM102'),
            ('Business Economics',        'BCOM103'), ('Business Communication',   'BCOM104')],
        2: [('Financial Accounting II',   'BCOM201'), ('Business Statistics',      'BCOM202'),
            ('Business Law',              'BCOM203'), ('Computer Applications',    'BCOM204')],
        3: [('Corporate Accounting I',    'BCOM301'), ('Cost Accounting',          'BCOM302'),
            ('Income Tax Law',            'BCOM303'), ('Banking & Finance',        'BCOM304')],
        4: [('Corporate Accounting II',   'BCOM401'), ('Management Accounting',    'BCOM402'),
            ('Auditing',                  'BCOM403'), ('Marketing Management',     'BCOM404')],
        5: [('Advanced Accounting',       'BCOM501'), ('Financial Management',     'BCOM502'),
            ('Goods & Services Tax',      'BCOM503'), ('Entrepreneurship',         'BCOM504')],
        6: [('Strategic Management',      'BCOM601'), ('Investment Management',    'BCOM602'),
            ('Project Work',              'BCOM603'), ('E-Commerce',               'BCOM604')],
    }
    # B.Sc Subjects (6 semesters)
    bsc_subjects = {
        1: [('Mathematics I',             'BSC101'), ('Physics I',                 'BSC102'),
            ('Chemistry I',               'BSC103'), ('English Communication',     'BSC104')],
        2: [('Mathematics II',            'BSC201'), ('Physics II',                'BSC202'),
            ('Chemistry II',              'BSC203'), ('Environmental Science',     'BSC204')],
        3: [('Linear Algebra',            'BSC301'), ('Classical Mechanics',       'BSC302'),
            ('Organic Chemistry',         'BSC303'), ('Statistics I',              'BSC304')],
        4: [('Real Analysis',             'BSC401'), ('Electromagnetism',          'BSC402'),
            ('Physical Chemistry',        'BSC403'), ('Statistics II',             'BSC404')],
        5: [('Numerical Methods',         'BSC501'), ('Quantum Mechanics',         'BSC502'),
            ('Spectroscopy',              'BSC503'), ('Research Methodology',      'BSC504')],
        6: [('Complex Analysis',          'BSC601'), ('Nuclear Physics',           'BSC602'),
            ('Industrial Chemistry',      'BSC603'), ('Project & Seminar',         'BSC604')],
    }
    # M.Com Subjects (4 semesters)
    mcom_subjects = {
        1: [('Advanced Financial Accounting', 'MCOM101'), ('Managerial Economics',    'MCOM102'),
            ('Business Research Methods',     'MCOM103'), ('Organisational Behaviour', 'MCOM104')],
        2: [('Advanced Cost Accounting',      'MCOM201'), ('Corporate Finance',        'MCOM202'),
            ('International Business',        'MCOM203'), ('Financial Markets',        'MCOM204')],
        3: [('Strategic Financial Mgmt',      'MCOM301'), ('Taxation Law & Practice',  'MCOM302'),
            ('Security Analysis',             'MCOM303'), ('Human Resource Mgmt',      'MCOM304')],
        4: [('Portfolio Management',          'MCOM401'), ('Corporate Governance',      'MCOM402'),
            ('Dissertation / Project',        'MCOM403'), ('Elective Paper',            'MCOM404')],
    }
    # MCA Subjects (4 semesters)
    mca_subjects = {
        1: [('Programming in Python',         'MCA101'), ('Data Structures & Algorithms', 'MCA102'),
            ('Database Management Systems',   'MCA103'), ('Computer Organisation',        'MCA104')],
        2: [('Operating Systems',             'MCA201'), ('Object-Oriented Programming',  'MCA202'),
            ('Web Technologies',              'MCA203'), ('Software Engineering',         'MCA204')],
        3: [('Machine Learning',              'MCA301'), ('Cloud Computing',              'MCA302'),
            ('Mobile Application Dev',        'MCA303'), ('Network Security',             'MCA304')],
        4: [('Artificial Intelligence',       'MCA401'), ('Big Data Analytics',           'MCA402'),
            ('Project Work',                  'MCA403'), ('Research Paper / Seminar',     'MCA404')],
    }

    all_subject_data = [
        ('BCOM', 'COM', bcom_subjects),
        ('BSC',  'SCI', bsc_subjects),
        ('MCOM', 'COM', mcom_subjects),
        ('MCA',  'MCA', mca_subjects),
    ]
    for ccode, dcode, smap in all_subject_data:
        cid = course_id(ccode)
        did = dept_id(dcode)
        for sem_no, subjs in smap.items():
            sid = sem_id(ccode, sem_no)
            for sname, scode in subjs:
                try: c.execute(
                    "INSERT INTO subjects (name,code,course_id,semester_id,department_id,credits) VALUES (?,?,?,?,?,4)",
                    (sname, scode, cid, sid, did))
                except: pass
    conn.commit()

    # ── SEED HOD USERS ────────────────────────────────────────────
    hod_users = [
        ('HOD Commerce',   'hod.commerce@university.edu',  hash_password('hod123'), 'hod', dept_id('COM')),
        ('HOD Science',    'hod.science@university.edu',   hash_password('hod123'), 'hod', dept_id('SCI')),
        ('HOD Comp. Apps', 'hod.mca@university.edu',       hash_password('hod123'), 'hod', dept_id('MCA')),
    ]
    for u in hod_users:
        try: c.execute("INSERT INTO users (name,email,password,role,department_id) VALUES (?,?,?,?,?)", u)
        except: pass
    conn.commit()

    # ── SEED FACULTY ─────────────────────────────────────────────
    faculty_users = [
        # (name, email, dept_code, emp_id, designation)
        ('Dr. Ramesh Patil',    'ramesh@university.edu',  'COM', 'FAC001', 'Professor'),
        ('Prof. Sunita Kulkarni','sunita@university.edu', 'COM', 'FAC002', 'Associate Professor'),
        ('Dr. Anil Joshi',      'anil@university.edu',    'SCI', 'FAC003', 'Professor'),
        ('Prof. Meera Nair',    'meera@university.edu',   'SCI', 'FAC004', 'Assistant Professor'),
        ('Dr. Vikram Shah',     'vikram@university.edu',  'MCA', 'FAC005', 'Professor'),
        ('Prof. Priya Desai',   'priya.d@university.edu', 'MCA', 'FAC006', 'Associate Professor'),
    ]
    for name, email, dcode, emp, desig in faculty_users:
        did = dept_id(dcode)
        try:
            c.execute("INSERT INTO users (name,email,password,role,department_id) VALUES (?,?,?,?,?)",
                      (name, email, hash_password('faculty123'), 'faculty', did))
            uid = c.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()['id']
            c.execute("INSERT INTO faculty (user_id,emp_id,department_id,designation) VALUES (?,?,?,?)",
                      (uid, emp, did, desig))
        except: pass
    conn.commit()

    # Assign faculty to subjects (faculty_id -> subjects)
    def fac_db_id(emp): return c.execute("SELECT id FROM faculty WHERE emp_id=?", (emp,)).fetchone()['id']

    # COM faculty → B.Com & M.Com subjects
    bcom_subj_ids = [r['id'] for r in c.execute("SELECT id FROM subjects WHERE code LIKE 'BCOM%'").fetchall()]
    mcom_subj_ids = [r['id'] for r in c.execute("SELECT id FROM subjects WHERE code LIKE 'MCOM%'").fetchall()]
    fac001 = fac_db_id('FAC001'); fac002 = fac_db_id('FAC002')
    for i, sid in enumerate(bcom_subj_ids):
        fid = fac001 if i % 2 == 0 else fac002
        c.execute("UPDATE subjects SET faculty_id=? WHERE id=?", (fid, sid))
    for i, sid in enumerate(mcom_subj_ids):
        fid = fac001 if i % 2 == 0 else fac002
        c.execute("UPDATE subjects SET faculty_id=? WHERE id=?", (fid, sid))

    # SCI faculty → B.Sc subjects
    bsc_subj_ids = [r['id'] for r in c.execute("SELECT id FROM subjects WHERE code LIKE 'BSC%'").fetchall()]
    fac003 = fac_db_id('FAC003'); fac004 = fac_db_id('FAC004')
    for i, sid in enumerate(bsc_subj_ids):
        fid = fac003 if i % 2 == 0 else fac004
        c.execute("UPDATE subjects SET faculty_id=? WHERE id=?", (fid, sid))

    # MCA faculty → MCA subjects
    mca_subj_ids = [r['id'] for r in c.execute("SELECT id FROM subjects WHERE code LIKE 'MCA%'").fetchall()]
    fac005 = fac_db_id('FAC005'); fac006 = fac_db_id('FAC006')
    for i, sid in enumerate(mca_subj_ids):
        fid = fac005 if i % 2 == 0 else fac006
        c.execute("UPDATE subjects SET faculty_id=? WHERE id=?", (fid, sid))
    conn.commit()

    # ── SEED STUDENTS ─────────────────────────────────────────────
    student_users = [
        # (name, email, course_code, year, semester_no, roll_no)
        ('Ananya Sharma',   'ananya@student.university.edu',   'BCOM', 2, 3, 'BCOM2023001'),
        ('Ravi Kumar',      'ravi@student.university.edu',     'BCOM', 3, 5, 'BCOM2022001'),
        ('Pooja Mehta',     'pooja@student.university.edu',    'BSC',  2, 3, 'BSC2023001'),
        ('Arjun Singh',     'arjun@student.university.edu',    'BSC',  1, 1, 'BSC2024001'),
        ('Divya Nair',      'divya@student.university.edu',    'MCOM', 1, 2, 'MCOM2024001'),
        ('Kiran Joshi',     'kiran@student.university.edu',    'MCOM', 2, 4, 'MCOM2023001'),
        ('Amit Patel',      'amit@student.university.edu',     'MCA',  1, 1, 'MCA2024001'),
        ('Sneha Verma',     'sneha@student.university.edu',    'MCA',  2, 3, 'MCA2023001'),
    ]

    for name, email, ccode, year, sem_no, roll in student_users:
        cid = course_id(ccode)
        row = c.execute("SELECT department_id FROM courses WHERE id=?", (cid,)).fetchone()
        did = row['department_id']
        sid_ref = sem_id(ccode, sem_no)
        try:
            c.execute("INSERT INTO users (name,email,password,role,department_id) VALUES (?,?,?,?,?)",
                      (name, email, hash_password('student123'), 'student', did))
            uid = c.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()['id']
            c.execute("INSERT INTO students (user_id,roll_no,course_id,department_id,semester_id,year,semester) VALUES (?,?,?,?,?,?,?)",
                      (uid, roll, cid, did, sid_ref, year, sem_no))
        except: pass
    conn.commit()

    # ── SEED MARKS ────────────────────────────────────────────────
    grade_map = [(90,'O'),(75,'A+'),(60,'A'),(50,'B'),(40,'C'),(0,'F')]
    def get_grade(t):
        for th, g in grade_map:
            if t >= th: return g
        return 'F'

    all_students = c.execute("SELECT s.id, s.semester_id, s.course_id, s.semester FROM students s").fetchall()
    for stu in all_students:
        subjs = c.execute("SELECT id FROM subjects WHERE semester_id=? AND course_id=?",
                          (stu['semester_id'], stu['course_id'])).fetchall()
        for sub in subjs:
            i1 = random.randint(12, 20); i2 = random.randint(12, 20); ext = random.randint(40, 75)
            total = i1 + i2 + ext
            try: c.execute(
                "INSERT INTO marks (student_id,subject_id,semester,internal1,internal2,external,total,grade) VALUES (?,?,?,?,?,?,?,?)",
                (stu['id'], sub['id'], stu['semester'], i1, i2, ext, total, get_grade(total)))
            except: pass

    # ── SEED ATTENDANCE ───────────────────────────────────────────
    today = date.today()
    for stu in all_students:
        subjs = c.execute("SELECT id FROM subjects WHERE semester_id=? AND course_id=?",
                          (stu['semester_id'], stu['course_id'])).fetchall()
        for sub in subjs:
            for d in range(30):
                dd = today - timedelta(days=d)
                if dd.weekday() < 5:
                    st = random.choices(['P','A','M'], weights=[75,15,10])[0]
                    try: c.execute("INSERT INTO attendance (student_id,subject_id,date,status) VALUES (?,?,?,?)",
                                   (stu['id'], sub['id'], str(dd), st))
                    except: pass

    # ── SEED NOTICES ─────────────────────────────────────────────
    for title, body, tag, color in [
        ('End Semester Examination Schedule', 'ESE for all courses commences April 28. Hall tickets from April 20.', 'EXAM', 'danger'),
        ('Semester Results Declared', 'Results for the last semester are now live on the portal.', 'RESULT', 'success'),
        ('Annual College Fest 2026', 'Annual fest March 28-30. Register for events and competitions.', 'EVENT', 'warning'),
        ('Campus Placement Drive', 'Multiple companies visiting next month. Register via ERP portal.', 'PLACEMENT', 'primary'),
        ('New Timetable Uploaded', 'Revised timetable for current semester effective immediately.', 'INFO', 'info'),
    ]:
        try: c.execute("INSERT INTO notices (title,body,tag,color) VALUES (?,?,?,?)", (title, body, tag, color))
        except: pass

    conn.commit()
    conn.close()
    print("✅ Database initialized with B.Com, B.Sc, M.Com, MCA structure!")

if __name__ == '__main__':
    init_db()
