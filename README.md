# 🎓 CampusAI v7.0

## Quick Start
```powershell
pip install -r requirements.txt
copy .env.example .env
# Edit .env → add GROQ_API_KEY
python main.py
```
Open: http://127.0.0.1:8001

## Demo Logins
Student: S001/pass123 · S002/pass123 · S003/pass123
Admin:   A001/admin123

## Files
frontend/index.html         ← Main HTML
frontend/static/css/style.css ← All styles
frontend/static/js/app.js   ← All JavaScript
api.py                      ← FastAPI backend
graph.py                    ← 5-agent pipeline
database.py                 ← SQLite
agents/                     ← 5 AI agents
