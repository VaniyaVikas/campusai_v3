"""config.py – CampusAI Complete Configuration"""
import os
from dotenv import load_dotenv
load_dotenv()

class Config:
    GROQ_API_KEY:    str  = os.getenv("GROQ_API_KEY", "")
    LLM_MODEL:       str  = os.getenv("LLM_MODEL",       "llama-3.3-70b-versatile")
    LLM_MODEL_FAST:  str  = os.getenv("LLM_MODEL_FAST",  "llama-3.1-8b-instant")
    EMBEDDING_MODEL: str  = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")

     # ── Pinecone (replaces FAISS) ─────────────────────────────────────────────
    PINECONE_API_KEY:   str = os.getenv("PINECONE_API_KEY",    "")
    PINECONE_INDEX:     str = os.getenv("PINECONE_INDEX_NAME", "papa")
    PINECONE_HOST:      str = os.getenv("PINECONE_HOST",       "")

    POLICIES_DIR:    str  = os.getenv("POLICIES_DIR",    "data/policies")
    SMTP_HOST:       str  = os.getenv("SMTP_HOST",  "smtp.gmail.com")
    SMTP_PORT:       int  = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USER:       str  = os.getenv("SMTP_USER",  "")
    SMTP_PASS:       str  = os.getenv("SMTP_PASS",  "")
    EMAIL_FROM:      str  = os.getenv("EMAIL_FROM", "CampusAI")
    APP_HOST:        str  = os.getenv("APP_HOST",   "127.0.0.1")
    APP_PORT:        int  = int(os.getenv("APP_PORT",  "8001"))
    DEBUG:           bool = os.getenv("DEBUG", "true").lower() == "true"
    MAX_SUPERVISOR_RETRIES: int = int(os.getenv("MAX_SUPERVISOR_RETRIES", "2"))
    FRONTEND_DIR:    str  = os.getenv("FRONTEND_DIR", "frontend")

cfg = Config()
