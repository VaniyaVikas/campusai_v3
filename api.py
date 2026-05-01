"""api.py – CampusAI Complete Backend v6.0"""
import os, time, uuid, asyncio, logging
from pathlib import Path
from typing import Optional
from collections import OrderedDict

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from graph import run_query
from tools.email_tool import send_email
from state import ActionType
from config import cfg
from database import (
    init_database, verify_login,
    get_student, get_all_students, add_student, update_student, delete_student,
    save_chat, get_chat_history, get_all_chats,
    save_ticket, get_tickets, get_all_tickets, update_ticket,
    get_deadlines, get_notices, add_notice, get_analytics,
)

logger = logging.getLogger(__name__)

app = FastAPI(title="CampusAI v7.0", version="7.0.0", docs_url="/api/docs")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

_traces: OrderedDict = OrderedDict()

@app.on_event("startup")
async def startup():
    init_database()

@app.middleware("http")
async def log_req(request: Request, call_next):
    t0 = time.time()
    r  = await call_next(request)
    if not request.url.path.startswith("/static"):
        logger.info(f"{request.method} {request.url.path} {r.status_code} ({round((time.time()-t0)*1000,1)}ms)")
    return r

# ── Models ────────────────────────────────────────────────────────────────────
class LoginReq(BaseModel):
    user_id: str; password: str; user_type: str = "student"

class QueryReq(BaseModel):
    query: str
    user_id: Optional[str] = None
    user_type: str = "student"
    student_email: Optional[str] = None
    student_name:  Optional[str] = None
    session_id:    Optional[str] = None

class StudentReq(BaseModel):
    student_id: str; name: str; email: str; password: str
    department: str=""; semester: int=1; cgpa: float=0.0
    attendance: float=75.0; fees_due: float=0.0; fees_paid: float=0.0
    backlogs: int=0; phone: str=""

class StudentUpdateReq(BaseModel):
    name: Optional[str]=None; email: Optional[str]=None
    department: Optional[str]=None; semester: Optional[int]=None
    cgpa: Optional[float]=None; attendance: Optional[float]=None
    fees_due: Optional[float]=None; fees_paid: Optional[float]=None
    backlogs: Optional[int]=None; phone: Optional[str]=None

class TicketUpdateReq(BaseModel):
    status: Optional[str]=None; assigned_to: Optional[str]=None
    resolution: Optional[str]=None; priority: Optional[str]=None

class NoticeReq(BaseModel):
    title: str; content: str; posted_by: str
    department: str="General"; priority: str="normal"

def _g(obj, key, default=None):
    if obj is None: return default
    return obj.get(key, default) if isinstance(obj, dict) else getattr(obj, key, default)

# ── AUTH ──────────────────────────────────────────────────────────────────────
@app.post("/auth/login")
async def login(req: LoginReq):
    user = verify_login(req.user_id, req.password, req.user_type)
    if not user: raise HTTPException(401, "Invalid ID or Password")
    user.pop("password_hash", None)
    return {"success": True, "user": user, "user_type": req.user_type}

# ── QUERY ─────────────────────────────────────────────────────────────────────
@app.post("/query")
async def handle_query(req: QueryReq):
    if not req.query.strip(): raise HTTPException(400, "Query cannot be empty")
    start = time.time()

    student_info = get_student(req.user_id) if req.user_id and req.user_type=="student" else None
    email = req.student_email or (student_info.get("email") if student_info else None)
    name  = req.student_name  or (student_info.get("name")  if student_info else None)

    loop  = asyncio.get_event_loop()
    state = await loop.run_in_executor(None, lambda: run_query(req.query, email, name))
    elapsed = round((time.time()-start)*1000, 1)

    action   = state.get("action")   or {}
    decision = state.get("decision") or {}

    ticket_id   = _g(action,"ticket_id") or f"TICKET-{uuid.uuid4().hex[:8].upper()}"
    outcome_str = str(_g(decision,"outcome","unknown")).replace("DecisionOutcome.","")
    lang_str    = str(state.get("detected_language","english")).replace("Language.","")

    try:
        save_chat(req.user_id, req.user_type, req.session_id or str(uuid.uuid4()),
                  req.query, state.get("final_response",""), state.get("intent",""),
                  outcome_str, float(_g(decision,"confidence",0.0)),
                  ticket_id, lang_str, state.get("emotion_detected","neutral"))
    except Exception as e: logger.error(f"save_chat: {e}")

    _traces[ticket_id] = {"ticket_id":ticket_id,"request":{"query":req.query,"user_id":req.user_id},
        "state":{"raw_query":state.get("raw_query"),"detected_language":lang_str,
                 "intent":state.get("intent"),"emotion_detected":state.get("emotion_detected","neutral"),
                 "entities":state.get("entities") or {},
                 "decision":{"outcome":outcome_str,"reasoning":_g(decision,"reasoning",""),
                             "confidence":_g(decision,"confidence",0.0),
                             "policy_references":_g(decision,"policy_references",[])},
                 "final_response":state.get("final_response"),
                 "supervisor_approved":state.get("supervisor_approved"),
                 "retry_count":state.get("retry_count",0),"errors":state.get("errors",[])},
        "elapsed_ms":elapsed}
    if len(_traces)>500: _traces.popitem(last=False)

    if email and _g(action,"action_type")==ActionType.EMAIL_REPLY and state.get("supervisor_approved"):
        asyncio.get_event_loop().run_in_executor(
            None, lambda: send_email(email, _g(action,"subject","Response"), state.get("final_response","")))

    return {"ticket_id":ticket_id,"response":state.get("final_response") or "Please contact helpdesk@college.edu",
            "language_detected":lang_str,"intent":state.get("intent") or "general_inquiry",
            "emotion_detected":state.get("emotion_detected") or "neutral",
            "decision_outcome":outcome_str,"decision_confidence":float(_g(decision,"confidence",0.0)),
            "decision_reasoning":str(_g(decision,"reasoning","")),"conditions":_g(decision,"conditions"),
            "supervisor_approved":bool(state.get("supervisor_approved")),
            "supervisor_feedback":str(state.get("supervisor_feedback") or ""),
            "supervisor_severity":str(state.get("supervisor_severity") or "low"),
            "form_suggestion":_g(action,"form_name") if isinstance(action,dict) else None,
            "policy_references":_g(decision,"policy_references",[]),
            "entities":state.get("entities") or {},"errors":state.get("errors") or [],
            "processing_time_ms":elapsed}

# ── STUDENTS ──────────────────────────────────────────────────────────────────
@app.get("/students")
async def students():
    ss=get_all_students(); [s.pop("password_hash",None) for s in ss]; return {"students":ss,"total":len(ss)}

@app.get("/students/{sid}")
async def student(sid:str):
    s=get_student(sid)
    if not s: raise HTTPException(404,"Not found")
    s.pop("password_hash",None); return s

@app.post("/students")
async def create_student(req:StudentReq):
    ok=add_student(req.dict())
    if not ok: raise HTTPException(400,"ID or Email already exists")
    return {"success":True,"student_id":req.student_id}

@app.patch("/students/{sid}")
async def upd_student(sid:str, req:StudentUpdateReq):
    return {"success":update_student(sid,req.dict(exclude_none=True))}

@app.delete("/students/{sid}")
async def del_student(sid:str): return {"success":delete_student(sid)}

# ── TICKETS ───────────────────────────────────────────────────────────────────
@app.get("/tickets")
async def all_tickets(): t=get_all_tickets(); return {"tickets":t,"total":len(t)}

@app.get("/tickets/student/{sid}")
async def stu_tickets(sid:str): return {"tickets":get_tickets(sid)}

@app.post("/tickets")
async def create_ticket(data:dict):
    tid=data.get("ticket_id") or f"TKT-{uuid.uuid4().hex[:6].upper()}"
    save_ticket(tid,data.get("student_id"),data.get("subject",""),
                data.get("description",""),data.get("department","Admin"),data.get("priority","medium"))
    return {"success":True,"ticket_id":tid}

@app.patch("/tickets/{tid}")
async def upd_ticket(tid:str, req:TicketUpdateReq):
    return {"success":update_ticket(tid,req.dict(exclude_none=True))}

# ── TRACES ────────────────────────────────────────────────────────────────────
@app.get("/trace/{tid}")
async def get_trace(tid:str):
    if tid not in _traces: raise HTTPException(404,"Not found")
    return _traces[tid]

@app.get("/traces")
async def list_traces(limit:int=50): return {"total":len(_traces),"traces":list(_traces.values())[-limit:]}

@app.delete("/clear-traces")
async def clear_traces(): _traces.clear(); return {"status":"cleared"}

# ── HISTORY ───────────────────────────────────────────────────────────────────
@app.get("/history/{uid}")
async def history(uid:str, limit:int=50): return {"history":get_chat_history(uid,limit)}

@app.get("/history")
async def all_hist(limit:int=100): return {"history":get_all_chats(limit)}

# ── DEADLINES & NOTICES ───────────────────────────────────────────────────────
@app.get("/deadlines")
async def deadlines(): return {"deadlines":get_deadlines()}

@app.get("/notices")
async def notices(): return {"notices":get_notices()}

@app.post("/notices")
async def post_notice(req:NoticeReq): return {"success":add_notice(req.title,req.content,req.posted_by,req.department,req.priority)}

# ── POLICIES ──────────────────────────────────────────────────────────────────
@app.get("/policies")
async def list_policies():
    pd=Path(cfg.POLICIES_DIR); policies=[]
    dept_desc={"exam":"ATKT, hall ticket, revaluation","admin":"Fee, admission, attendance",
               "placement":"Placement, helpdesk, grievance","general":"General info, FAQs"}
    if pd.exists():
        for f in sorted(pd.iterdir()):
            if f.suffix.lower() in (".pdf",".txt"):
                dept=f.stem.split("_")[0] if "_" in f.stem else "general"
                policies.append({"name":f.name,"department":dept,"description":dept_desc.get(dept,"Policy document"),"size_kb":round(f.stat().st_size/1024,1)})
    return {"total":len(policies),"policies":policies}

@app.post("/ingest")
async def trigger_ingest():
    async def _run():
        proc=await asyncio.create_subprocess_exec("python","tools/ingest_policies.py","--force",
             stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
        await proc.communicate()
        import agents.policy_agent as pa; pa._vectorstore=None
    asyncio.create_task(_run()); return {"status":"started"}

# ── ANALYTICS ─────────────────────────────────────────────────────────────────
@app.get("/analytics")
async def analytics(): return get_analytics()

# ── HEALTH ────────────────────────────────────────────────────────────────────
@app.get("/health")
async def health():
    from agents.policy_agent import _vectorstore
    return {"status":"ok","version":"7.0.0","model":cfg.LLM_MODEL,"fast_model":cfg.LLM_MODEL_FAST,
            "index_loaded":_vectorstore is not None,"index_exists":_vectorstore is not None,"traces":len(_traces)}

# ── SERVE FRONTEND ────────────────────────────────────────────────────────────
import sys as _sys
_BASE = Path(__file__).parent
frontend_dir = _BASE / cfg.FRONTEND_DIR
static_dir   = frontend_dir / "static" 

@app.on_event("startup")
async def mount_static():
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

@app.get("/", include_in_schema=False)
async def index():
    f = frontend_dir/"index.html"
    return FileResponse(str(f)) if f.exists() else JSONResponse({"error":"Frontend not found"})

@app.get("/{path:path}", include_in_schema=False)
async def spa(path:str):
    skip=("static/","auth","query","trace","traces","history","students","tickets",
          "deadlines","notices","analytics","ingest","policies","health","api/","clear-traces")
    if any(path.startswith(s) for s in skip): raise HTTPException(404)
    f = frontend_dir/"index.html"
    return FileResponse(str(f)) if f.exists() else JSONResponse({"error":"Not found"})
