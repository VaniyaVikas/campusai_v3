
import logging
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import StateGraph, END
from state import AgentState
from agents import (
    query_understanding_agent, policy_agent, decision_agent,
    action_agent, supervisor_agent, should_rollback,
)
from llm_factory import get_llm, safe_invoke

logger = logging.getLogger(__name__)

GREETING_WORDS = {
    "hi","hello","hey","helo","hii","hiii","yo","heyy",
    "namaste","namaskar","kem cho","kem chho","kem",
    "kaise ho","kya hal","kya haal","good morning","good afternoon",
    "good evening","good night","how are you","how r u","whats up",
    "what's up","sup","wassup","hola","greetings","howdy",
    "kem cho bhai","kem cho yaar","helo bhai","hi bhai","hello bhai",
}
THANKS_WORDS = {
    "thanks","thank you","thank","dhanyavad","shukriya",
    "ok","okay","got it","understood","sure","great",
    "nice","cool","bye","goodbye","alright","perfect","awesome",
    "thik che","saru","barobar","maja ni","maja","mast",
}

DIRECT_SYSTEM = """You are CampusAI — a warm, friendly, intelligent assistant for Indian college students.

You can help with:
- College queries: ATKT, fees, attendance, placement, exams, scholarships, hall tickets
- General questions: science, math, history, coding, GK, career advice, anything!
- Casual chat: jokes, motivation, riddles, friendly conversation

Language rules:
- Gujarati query → respond in Gujarati (Gujarati script preferred, or Hinglish ok)
- Hinglish query → respond in Hinglish (Hindi+English Roman mix)  
- English → respond in English
- Mixed → respond in same mix

Behavior:
- For greetings → greet warmly, ask how you can help
- For thanks/bye → respond warmly
- For general knowledge (history, science, coding, math, etc.) → answer helpfully and clearly
- For jokes/fun → be witty and fun
- For motivation → be encouraging
- For college queries → give helpful info and suggest visiting admin if needed
- NEVER say "I can only answer college queries" — you can answer ANYTHING
- Keep responses concise (2-5 sentences for simple queries, more for complex)
- Plain text only, no markdown symbols like ** or ##
- Be conversational and friendly like a helpful senior student"""


def _route(state: AgentState) -> str:
    raw    = (state.get("raw_query") or "").lower().strip().rstrip("!?. ")
    intent = (state.get("intent") or "").lower()
    spam   = state.get("spam_flag", False)

    # Spam → direct (will give polite response)
    if spam: return "direct"

    # Pure greetings → direct
    if raw in GREETING_WORDS: return "direct"
    if any(raw.startswith(g+" ") for g in GREETING_WORDS): return "direct"
    if raw in THANKS_WORDS: return "direct"

    # General inquiry → direct (LLM handles it)
    if intent in ("general_inquiry", "general"): return "direct"

    # Short queries (less than 4 words) that aren't college-specific → direct
    words = raw.split()
    if len(words) <= 3 and intent == "general_inquiry": return "direct"

    # Everything else → full pipeline
    return "pipeline"


def direct_response_node(state: AgentState) -> AgentState:
    import uuid
    from state import ActionRecord, ActionType, DecisionRecord, DecisionOutcome

    raw  = state.get("raw_query", "")

    try:
        llm = get_llm(temperature=0.6, fast=False)
        response = safe_invoke(
            llm,
            [SystemMessage(content=DIRECT_SYSTEM),
             HumanMessage(content=f"Student: {raw}")],
            context="DirectResponse"
        )
    except Exception as e:
        logger.error(f"DirectResponse error: {e}")
        response = (
            "Namaste! I'm CampusAI — your college assistant and general helper! "
            "I can help with ATKT, fees, attendance, exams, and also general questions. "
            "What do you need help with?"
        )

    tid    = f"TICKET-{uuid.uuid4().hex[:8].upper()}"
    action = ActionRecord(
        action_type=ActionType.INFORMATION_ONLY, subject=None,
        body=response, recipient=None, form_name=None, ticket_id=tid, sent=False
    )
    decision = DecisionRecord(
        outcome=DecisionOutcome.ALLOWED,
        reasoning="Direct response — general query handled by LLM.",
        policy_references=[], confidence=1.0, conditions=None,
        confidence_explanation="General query — direct LLM response."
    )
    return {
        **state,
        "decision": decision, "action": action, "final_response": response,
        "supervisor_approved": True, "supervisor_feedback": "Auto-approved: direct.",
        "supervisor_severity": "low", "retrieved_policies": [], "policy_summary": "",
        "retry_count": 0
    }


def build_graph():
    g = StateGraph(AgentState)
    g.add_node("query_understanding", query_understanding_agent)
    g.add_node("direct_response",     direct_response_node)
    g.add_node("policy",              policy_agent)
    g.add_node("decision",            decision_agent)
    g.add_node("action",              action_agent)
    g.add_node("supervisor",          supervisor_agent)
    g.set_entry_point("query_understanding")
    g.add_conditional_edges("query_understanding", _route,
                            {"direct":"direct_response","pipeline":"policy"})
    g.add_edge("direct_response", END)
    g.add_edge("policy",   "decision")
    g.add_edge("decision", "action")
    g.add_edge("action",   "supervisor")
    g.add_conditional_edges("supervisor", should_rollback,
                            {"approved":END,"rollback":"decision"})
    return g.compile()

compiled_graph = build_graph()

def run_query(raw_query, student_email=None, student_name=None):
    state = {
        "raw_query": raw_query, "student_email": student_email, "student_name": student_name,
        "detected_language": None, "normalized_query": None, "intent": None, "entities": None,
        "emotion_detected": None, "spam_flag": False, "retrieved_policies": None,
        "policy_summary": None, "decision": None, "action": None, "final_response": None,
        "supervisor_approved": None, "supervisor_feedback": None, "supervisor_severity": None,
        "retry_count": 0, "errors": [],
    }
    try:
        logger.info(f"Pipeline START | {raw_query[:60]!r}")
        result = compiled_graph.invoke(state)
        logger.info(f"Pipeline END | approved={result.get('supervisor_approved')} retries={result.get('retry_count',0)}")
        return result
    except Exception as exc:
        logger.exception(f"Pipeline FATAL: {exc}")
        fb = dict(state)
        fb.update({
            "final_response": "Technical issue — please contact helpdesk@college.edu or visit Admin Office (Mon-Sat 9AM-5PM).",
            "supervisor_approved": True, "supervisor_severity": "high", "errors": [str(exc)]
        })
        return fb
