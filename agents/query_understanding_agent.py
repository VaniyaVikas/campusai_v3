
import json
import re
import logging

from langchain_core.messages import HumanMessage, SystemMessage
from state import AgentState, Language
from llm_factory import get_llm, safe_invoke

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a multilingual query understanding engine for a college administration system.
You receive student queries in English, Gujarati, Hinglish, or a mix.

Output ONLY a valid JSON object with NO markdown fences, NO explanation:
{
  "detected_language": "english" | "gujarati" | "hinglish" | "unknown",
  "normalized_query": "<English restatement of the student intent, clear and concise>",
  "intent": "<snake_case label — see list below>",
  "entities": {"<key>": "<value>"},
  "emotion_detected": "neutral" | "urgent" | "frustrated" | "confused" | "anxious" | "happy",
  "spam_flag": false
}

Intent options:
- atkt_form_eligibility
- fee_payment_deadline
- exam_schedule
- placement_eligibility
- hall_ticket
- result_query
- attendance_policy
- admission_query
- grievance
- general_inquiry   ← use this for greetings, casual chat, general knowledge, jokes, math, coding, etc.

Rules:
- normalized_query MUST be in English.
- spam_flag = false for almost everything. Only true if it is genuinely offensive/harmful.
- General knowledge (history, science, coding, jokes, motivation) → intent = "general_inquiry"
- Greetings, thanks, bye → intent = "general_inquiry"
"""


def _extract_json(raw: str) -> dict:
    cleaned = re.sub(r"```(?:json)?", "", raw).strip().rstrip("`").strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    brace_count = 0
    start = -1
    for i, ch in enumerate(cleaned):
        if ch == "{":
            if start == -1:
                start = i
            brace_count += 1
        elif ch == "}":
            brace_count -= 1
            if brace_count == 0 and start != -1:
                try:
                    return json.loads(cleaned[start: i + 1])
                except json.JSONDecodeError:
                    break
    raise ValueError(f"Cannot extract JSON from: {raw[:200]}")


_GREETINGS = {
    "hi","hello","hey","helo","hii","hiii","hiiii","yo","heyy",
    "namaste","namaskar","kem cho","kem chho","kem",
    "kaise ho","kya hal","kya haal","good morning","good afternoon",
    "good evening","good night","how are you","how r u","how ru",
    "whats up","what's up","sup","wassup","hola","greetings","howdy",
    "kem cho bhai","kem cho yaar","helo bhai","hi bhai","hello bhai",
}
_THANKS = {
    "thanks","thank you","thank","dhanyavad","shukriya",
    "ok","okay","got it","understood","sure","great","nice",
    "cool","bye","goodbye","alright","perfect","awesome",
    "thik che","saru","barobar","maja ni","maja","mast",
}


def query_understanding_agent(state: AgentState) -> AgentState:
    raw     = (state.get("raw_query") or "").strip()
    q_lower = raw.lower().strip().rstrip("!?. ")

    # Fast-path: greetings
    if q_lower in _GREETINGS or any(q_lower.startswith(g+" ") for g in _GREETINGS):
        return {**state, "detected_language": Language.ENGLISH,
                "normalized_query": raw, "intent": "general_inquiry",
                "entities": {}, "emotion_detected": "happy", "spam_flag": False}
    if q_lower in _THANKS:
        return {**state, "detected_language": Language.ENGLISH,
                "normalized_query": raw, "intent": "general_inquiry",
                "entities": {}, "emotion_detected": "neutral", "spam_flag": False}

    llm = get_llm(temperature=0.0, fast=True)
    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=f"Student query: {state['raw_query']}"),
    ]

    try:
        raw_resp = safe_invoke(llm, messages, context="QueryUnderstandingAgent")
        parsed = _extract_json(raw_resp)

        lang_str = str(parsed.get("detected_language", "unknown")).lower()
        try:
            detected_language = Language(lang_str)
        except ValueError:
            detected_language = Language.UNKNOWN

        entities = parsed.get("entities", {})
        if not isinstance(entities, dict):
            entities = {}

        return {
            **state,
            "detected_language": detected_language,
            "normalized_query":  parsed.get("normalized_query") or state["raw_query"],
            "intent":            parsed.get("intent", "general_inquiry"),
            "entities":          entities,
            "emotion_detected":  parsed.get("emotion_detected", "neutral"),
            "spam_flag":         bool(parsed.get("spam_flag", False)),
        }

    except Exception as e:
        logger.warning(f"QueryUnderstandingAgent fallback: {e}")
        return {
            **state,
            "detected_language": Language.UNKNOWN,
            "normalized_query":  state["raw_query"],
            "intent":            "general_inquiry",
            "entities":          {},
            "emotion_detected":  "neutral",
            "spam_flag":         False,
            "errors": state.get("errors", []) + [f"QueryUnderstandingAgent error: {e}"],
        }
