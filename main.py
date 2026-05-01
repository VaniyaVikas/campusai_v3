
import os, sys, logging, subprocess
from pathlib import Path

def setup_logging():
    logging.basicConfig(level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s", datefmt="%H:%M:%S")
    for n in ["sentence_transformers","transformers","httpx","httpcore","faiss","watchfiles","urllib3"]:
        logging.getLogger(n).setLevel(logging.WARNING)

def fix_env():
    env = Path(".env")
    if not env.exists():
        if Path(".env.example").exists():
            import shutil; shutil.copy(".env.example",".env")
            print("  .env created — add your GROQ_API_KEY!")
        return
    content = env.read_text(encoding="utf-8")
    import re; changed = False
    bad = ["all-MiniLM","all-minilm","paraphrase-multilingual","sentence-transformers","MiniLM"]
    for b in bad:
        if re.search(rf"LLM_MODEL_FAST=.*{b}", content, re.IGNORECASE):
            content = re.sub(r"LLM_MODEL_FAST=.*","LLM_MODEL_FAST=llama-3.1-8b-instant",content)
            changed = True; print(" Fixed: LLM_MODEL_FAST → llama-3.1-8b-instant")
    for old,new in [("llama3-70b-8192","llama-3.3-70b-versatile"),("llama3-8b-8192","llama-3.1-8b-instant")]:
        if old in content:
            content = content.replace(old, new); changed = True; print(f" Fixed: {old} → {new}")
    if changed:
        env.write_text(content, encoding="utf-8")
    from dotenv import load_dotenv; load_dotenv(override=True)

def check_key():
    from dotenv import load_dotenv; load_dotenv(override=True)
    key = os.getenv("GROQ_API_KEY","")
    if not key or key == "your_groq_api_key_here":
        print("\n" + "="*52 + "\n  GROQ_API_KEY not set!\n  Edit .env and add your key\n  Get free key: https://console.groq.com\n" + "="*52)
        sys.exit(1)
    print(f"API key: {key[:8]}...")

def auto_ingest():
    from dotenv import load_dotenv; load_dotenv(override=True)
    idx = os.getenv("FAISS_INDEX_PATH","data/faiss_index")
    pol = os.getenv("POLICIES_DIR","data/policies")
    if Path(idx).exists():
        print(" FAISS index found"); return
    if not Path(pol).exists() or not list(Path(pol).glob("*.txt")):
        print(f"  No policy files in {pol} — add .txt files and re-run"); return
    print("\n Auto-ingesting policies (~30 sec)...")
    r = subprocess.run([sys.executable,"tools/ingest_policies.py"], capture_output=False)
    if r.returncode==0: print(" Ingest done!\n")

if __name__ == "__main__":
    setup_logging()
    print("\n" + "="*52)
    print("  🎓 CampusAI v7.0 — College Administration AI")
    print("="*52)
    print("\n🔧 Pre-flight checks...")
    fix_env(); check_key(); auto_ingest()
    from config import cfg
    print("\n" + "="*52)
    print(f"  Open  →  http://127.0.0.1:{cfg.APP_PORT}")
    print(f"  Docs  →  http://127.0.0.1:{cfg.APP_PORT}/api/docs")
    print(f"  Model →  {cfg.LLM_MODEL}")
    print(f"  Fast  →  {cfg.LLM_MODEL_FAST}")
    print("="*52 + "\n")
    import uvicorn
    uvicorn.run("api:app", host=cfg.APP_HOST, port=cfg.APP_PORT,
                reload=cfg.DEBUG, log_level="info")
