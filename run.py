import os, sys

from database.db_setup import init_db, DB_PATH
if not os.path.exists(DB_PATH):
    print("🔧 Initialising database...")
    init_db()
    print("✅ Database ready!")
else:
    print("✅ Database found.")

from app import app
print("\n" + "="*55)
print("🎓 College Academic Management System")
print("="*55)
print("🌐  URL : http://localhost:5000")
print("\n📋 Demo Credentials:")
print("  👨‍🎓 Student  : ananya@student.university.edu / student123")
print("  👩‍🏫 Faculty  : ramesh@university.edu          / faculty123")
print("  🏢 HOD(COM) : hod.commerce@university.edu    / hod123")
print("  🏢 HOD(SCI) : hod.science@university.edu     / hod123")
print("  🏢 HOD(MCA) : hod.mca@university.edu         / hod123")
print("="*55 + "\n")
app.run(debug=True, port=5000, host='0.0.0.0')
