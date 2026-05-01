
import sqlite3, hashlib, uuid, logging
from pathlib import Path
from datetime import datetime, date

logger = logging.getLogger(__name__)
DB_PATH = "data/campus.db"


def _conn():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    return c


def _hash(pw: str) -> str:
    return hashlib.sha256(pw.encode()).hexdigest()


def init_database():
    Path("data").mkdir(exist_ok=True)
    with _conn() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS students (
            student_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            department TEXT DEFAULT '',
            semester INTEGER DEFAULT 1,
            cgpa REAL DEFAULT 0.0,
            attendance REAL DEFAULT 75.0,
            fees_due REAL DEFAULT 0.0,
            fees_paid REAL DEFAULT 0.0,
            backlogs INTEGER DEFAULT 0,
            phone TEXT DEFAULT '',
            active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS admins (
            admin_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT DEFAULT 'admin',
            department TEXT DEFAULT 'All',
            active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS chat_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            user_type TEXT DEFAULT 'student',
            session_id TEXT,
            query TEXT NOT NULL,
            response TEXT,
            intent TEXT,
            decision TEXT,
            confidence REAL DEFAULT 0.0,
            ticket_id TEXT,
            language TEXT DEFAULT 'english',
            emotion TEXT DEFAULT 'neutral',
            timestamp TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS tickets (
            ticket_id TEXT PRIMARY KEY,
            student_id TEXT,
            subject TEXT,
            description TEXT,
            department TEXT DEFAULT 'Admin',
            priority TEXT DEFAULT 'medium',
            status TEXT DEFAULT 'open',
            assigned_to TEXT,
            resolution TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS deadlines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT,
            deadline_date TEXT NOT NULL,
            event_type TEXT DEFAULT 'general',
            department TEXT DEFAULT 'All',
            urgent INTEGER DEFAULT 0,
            active INTEGER DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS notices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            content TEXT,
            posted_by TEXT DEFAULT 'Admin',
            department TEXT DEFAULT 'General',
            priority TEXT DEFAULT 'normal',
            active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now'))
        );
        """)
        _seed_demo_data(c)
    logger.info("✓ Database initialized")


def _seed_demo_data(c):
    # Students
    students = [
        ("S001","Arjun Patel",   "arjun@gtu.ac.in",  "pass123","Computer Science",5,8.5,82.0,0,45000,0,"9876543210"),
        ("S002","Priya Shah",    "priya@gtu.ac.in",   "pass123","Electronics",     3,6.8,65.0,15000,30000,2,"9876543211"),
        ("S003","Rohan Mehta",   "rohan@gtu.ac.in",   "pass123","Mechanical",      7,9.1,91.0,0,50000,0,"9876543212"),
        ("S004","Sneha Desai",   "sneha@gtu.ac.in",   "pass123","Civil",           4,7.2,78.0,8000,35000,1,"9876543213"),
        ("S005","Kiran Kumar",   "kiran@gtu.ac.in",   "pass123","Information Technology",6,8.0,88.0,0,42000,0,"9876543214"),
    ]
    for s in students:
        c.execute("INSERT OR IGNORE INTO students VALUES (?,?,?,?,?,?,?,?,?,?,?,?,1,datetime('now'))",
                  (s[0],s[1],s[2],_hash(s[3]),s[4],s[5],s[6],s[7],s[8],s[9],s[10],s[11]))

    # Admins
    admins = [
        ("A001","Dr. Rajesh Kumar","rajesh@gtu.ac.in","admin123","superadmin","All"),
        ("A002","Prof. Meena Shah","meena@gtu.ac.in", "admin123","exam_admin","Examination"),
        ("A003","Mr. Vikram Patel","vikram@gtu.ac.in","admin123","accounts",  "Accounts"),
    ]
    for a in admins:
        c.execute("INSERT OR IGNORE INTO admins VALUES (?,?,?,?,?,?,1,datetime('now'))",
                  (a[0],a[1],a[2],_hash(a[3]),a[4],a[5]))

    # Deadlines
    deadlines = [
        ("ATKT Form Submission","Submit ATKT examination form","2026-04-15","exam","All",1),
        ("Semester Fees Last Date","Pay semester fees to avoid fine","2026-04-10","fees","All",1),
        ("Hall Ticket Collection","Collect hall ticket from exam dept","2026-04-20","exam","All",0),
        ("Placement Registration","Register on placement portal","2026-04-25","placement","All",0),
        ("Internal Assessment","Submit all internal marks","2026-04-05","exam","All",1),
    ]
    for d in deadlines:
        c.execute("INSERT OR IGNORE INTO deadlines(title,description,deadline_date,event_type,department,urgent) VALUES (?,?,?,?,?,?)", d)

    # Notices
    notices = [
        ("Exam Schedule Released","End semester examination schedule has been released. Check your timetable on the portal.","Dr. Rajesh Kumar","All","high"),
        ("Fee Payment Reminder","Last date for semester fee payment is April 10. Late fee of Rs.50/day will be charged.","Mr. Vikram Patel","Accounts","high"),
        ("Placement Drive - TCS","TCS campus placement drive on April 28. Register before April 25.","Placement Cell","Placement","normal"),
        ("Holiday Notice","College will remain closed on April 14 (Ambedkar Jayanti).","Administration","All","normal"),
    ]
    for n in notices:
        c.execute("INSERT OR IGNORE INTO notices(title,content,posted_by,department,priority) VALUES (?,?,?,?,?)", n)

    # Sample tickets
    tickets = [
        ("TKT-001","S002","ATKT Form Not Processing","My ATKT form payment failed but amount was deducted.","Accounts","high","open",None,None),
        ("TKT-002","S004","Attendance Shortage Appeal","Medical leave of 12 days not counted. Please update attendance.","Academic","medium","in_progress","Dr. Rajesh Kumar",None),
        ("TKT-003","S001","Scholarship Certificate Required","Need scholarship certificate for bank loan application.","Accounts","low","resolved",None,"Certificate issued on March 20, 2026."),
    ]
    for t in tickets:
        c.execute("INSERT OR IGNORE INTO tickets(ticket_id,student_id,subject,description,department,priority,status,assigned_to,resolution) VALUES (?,?,?,?,?,?,?,?,?)", t)


# ── Auth ──────────────────────────────────────────────────────────────────────
def verify_login(user_id: str, password: str, user_type: str) -> dict | None:
    table = "students" if user_type == "student" else "admins"
    id_col = "student_id" if user_type == "student" else "admin_id"
    with _conn() as c:
        row = c.execute(f"SELECT * FROM {table} WHERE {id_col}=? AND password_hash=? AND active=1",
                        (user_id, _hash(password))).fetchone()
        return dict(row) if row else None


# ── Students ──────────────────────────────────────────────────────────────────
def get_student(sid: str) -> dict | None:
    with _conn() as c:
        row = c.execute("SELECT * FROM students WHERE student_id=?", (sid,)).fetchone()
        return dict(row) if row else None

def get_all_students() -> list:
    with _conn() as c:
        return [dict(r) for r in c.execute("SELECT * FROM students WHERE active=1 ORDER BY student_id").fetchall()]

def add_student(data: dict) -> bool:
    try:
        with _conn() as c:
            c.execute("""INSERT INTO students
                (student_id,name,email,password_hash,department,semester,cgpa,attendance,fees_due,fees_paid,backlogs,phone)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (data["student_id"],data["name"],data["email"],_hash(data.get("password","pass123")),
                 data.get("department",""),data.get("semester",1),data.get("cgpa",0.0),
                 data.get("attendance",75.0),data.get("fees_due",0.0),data.get("fees_paid",0.0),
                 data.get("backlogs",0),data.get("phone","")))
        return True
    except Exception as e:
        logger.error(f"add_student: {e}"); return False

def update_student(sid: str, data: dict) -> bool:
    allowed = {"name","email","department","semester","cgpa","attendance","fees_due","fees_paid","backlogs","phone"}
    fields  = {k:v for k,v in data.items() if k in allowed}
    if not fields: return False
    sets = ", ".join(f"{k}=?" for k in fields)
    try:
        with _conn() as c:
            c.execute(f"UPDATE students SET {sets} WHERE student_id=?", (*fields.values(), sid))
        return True
    except Exception as e:
        logger.error(f"update_student: {e}"); return False

def delete_student(sid: str) -> bool:
    try:
        with _conn() as c:
            c.execute("UPDATE students SET active=0 WHERE student_id=?", (sid,))
        return True
    except: return False


# ── Chat History ──────────────────────────────────────────────────────────────
def save_chat(user_id, user_type, session_id, query, response, intent, decision, confidence, ticket_id, language, emotion):
    try:
        with _conn() as c:
            c.execute("""INSERT INTO chat_history
                (user_id,user_type,session_id,query,response,intent,decision,confidence,ticket_id,language,emotion)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (user_id,user_type,session_id,query,response,intent,decision,confidence,ticket_id,language,emotion))
    except Exception as e: logger.error(f"save_chat: {e}")

def get_chat_history(user_id: str, limit: int = 50) -> list:
    with _conn() as c:
        rows = c.execute("SELECT * FROM chat_history WHERE user_id=? ORDER BY timestamp DESC LIMIT ?",
                         (user_id, limit)).fetchall()
        return [dict(r) for r in rows]

def get_all_chats(limit: int = 100) -> list:
    with _conn() as c:
        rows = c.execute("SELECT * FROM chat_history ORDER BY timestamp DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]


# ── Tickets ───────────────────────────────────────────────────────────────────
def save_ticket(ticket_id, student_id, subject, description, department, priority):
    try:
        with _conn() as c:
            c.execute("INSERT OR IGNORE INTO tickets(ticket_id,student_id,subject,description,department,priority) VALUES (?,?,?,?,?,?)",
                      (ticket_id,student_id,subject,description,department,priority))
    except Exception as e: logger.error(f"save_ticket: {e}")

def get_tickets(student_id: str) -> list:
    with _conn() as c:
        rows = c.execute("SELECT * FROM tickets WHERE student_id=? ORDER BY created_at DESC", (student_id,)).fetchall()
        return [dict(r) for r in rows]

def get_all_tickets() -> list:
    with _conn() as c:
        rows = c.execute("SELECT * FROM tickets ORDER BY created_at DESC").fetchall()
        return [dict(r) for r in rows]

def update_ticket(ticket_id: str, data: dict) -> bool:
    allowed = {"status","assigned_to","resolution","priority"}
    fields  = {k:v for k,v in data.items() if k in allowed}
    if not fields: return False
    sets = ", ".join(f"{k}=?" for k in fields)
    try:
        with _conn() as c:
            c.execute(f"UPDATE tickets SET {sets}, updated_at=datetime('now') WHERE ticket_id=?",
                      (*fields.values(), ticket_id))
        return True
    except: return False


# ── Deadlines & Notices ───────────────────────────────────────────────────────
def get_deadlines() -> list:
    with _conn() as c:
        rows = c.execute("SELECT * FROM deadlines WHERE active=1 ORDER BY deadline_date ASC").fetchall()
        return [dict(r) for r in rows]

def get_notices() -> list:
    with _conn() as c:
        rows = c.execute("SELECT * FROM notices WHERE active=1 ORDER BY created_at DESC").fetchall()
        return [dict(r) for r in rows]

def add_notice(title, content, posted_by, department, priority) -> bool:
    try:
        with _conn() as c:
            c.execute("INSERT INTO notices(title,content,posted_by,department,priority) VALUES (?,?,?,?,?)",
                      (title,content,posted_by,department,priority))
        return True
    except: return False


# ── Analytics ─────────────────────────────────────────────────────────────────
def get_analytics() -> dict:
    with _conn() as c:
        total    = c.execute("SELECT COUNT(*) FROM chat_history").fetchone()[0]
        intents  = c.execute("SELECT intent, COUNT(*) as c FROM chat_history GROUP BY intent ORDER BY c DESC LIMIT 8").fetchall()
        langs    = c.execute("SELECT language, COUNT(*) as c FROM chat_history GROUP BY language").fetchall()
        daily    = c.execute("SELECT DATE(timestamp) as day, COUNT(*) as c FROM chat_history GROUP BY day ORDER BY day DESC LIMIT 7").fetchall()
        tick_st  = c.execute("SELECT status, COUNT(*) as c FROM tickets GROUP BY status").fetchall()
        dept_ld  = c.execute("SELECT department, COUNT(*) as c FROM tickets GROUP BY department ORDER BY c DESC LIMIT 6").fetchall()
    return {
        "total_queries": total,
        "top_intents":   [{"intent":r[0],"c":r[1]} for r in intents],
        "languages":     [{"language":r[0],"c":r[1]} for r in langs],
        "daily":         [{"day":r[0],"c":r[1]} for r in daily],
        "ticket_stats":  [{"status":r[0],"c":r[1]} for r in tick_st],
        "dept_load":     [{"department":r[0],"c":r[1]} for r in dept_ld],
    }
