
from __future__ import annotations
from typing import TypedDict, Optional, List, Any
from enum import Enum


class Language(str, Enum):
    ENGLISH  = "english"
    GUJARATI = "gujarati"
    HINGLISH = "hinglish"
    UNKNOWN  = "unknown"


class DecisionOutcome(str, Enum):
    ALLOWED           = "allowed"
    NOT_ALLOWED       = "not_allowed"
    CONDITIONAL       = "conditional"
    INSUFFICIENT_INFO = "insufficient_info"


class ActionType(str, Enum):
    EMAIL_REPLY       = "email_reply"
    FORM_SUGGESTION   = "form_suggestion"
    TICKET_CREATE     = "ticket_create"
    INFORMATION_ONLY  = "information_only"


class PolicyChunk(TypedDict):
    content:    str
    source:     str
    department: str
    score:      float


class DecisionRecord(TypedDict):
    outcome:            DecisionOutcome
    reasoning:          str
    policy_references:  List[str]
    confidence:         float
    conditions:         Optional[str]
    # FIX: added explanation field used by supervisor for better validation
    confidence_explanation: Optional[str]


class ActionRecord(TypedDict):
    action_type: ActionType
    subject:     Optional[str]
    body:        str
    recipient:   Optional[str]
    form_name:   Optional[str]
    ticket_id:   Optional[str]
    sent:        bool


class AgentState(TypedDict):
    # ── Input ──────────────────────────────────────────────────────────
    raw_query:     str
    student_email: Optional[str]
    student_name:  Optional[str]

    # ── Query Understanding Agent 
    detected_language:  Optional[Language]
    normalized_query:   Optional[str]
    intent:             Optional[str]
    entities:           Optional[dict]
    # FIX: new fields from query agent
    emotion_detected:   Optional[str]   # e.g. "urgent", "frustrated", "confused"
    spam_flag:          Optional[bool]  # True if query is irrelevant/spam

    # ── Policy Agent
    retrieved_policies: Optional[List[PolicyChunk]]
    policy_summary:     Optional[str]

    # ── Decision Agent 
    decision: Optional[DecisionRecord]

    # ── Action Agent ──────
    action:         Optional[ActionRecord]
    final_response: Optional[str]

    # ── Supervisor ─────────
    supervisor_approved:  Optional[bool]
    supervisor_feedback:  Optional[str]
    # FIX: supervisor now also stores its parsed severity
    supervisor_severity:  Optional[str]
    retry_count:          int
    errors:               List[str]
