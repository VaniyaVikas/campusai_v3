"""
tests/test_agents.py
Unit tests for each agent using mocked LLM responses.
Run with: pytest tests/ -v
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import json
import pytest
from unittest.mock import patch, MagicMock
from state import AgentState, Language, DecisionOutcome, ActionType


def _base_state(**kwargs) -> AgentState:
    defaults = dict(
        raw_query="test query",
        student_email=None,
        student_name=None,
        detected_language=None,
        normalized_query=None,
        intent=None,
        entities=None,
        retrieved_policies=None,
        policy_summary=None,
        decision=None,
        action=None,
        final_response=None,
        supervisor_approved=None,
        supervisor_feedback=None,
        retry_count=0,
        errors=[],
    )
    defaults.update(kwargs)
    return defaults


# ── Query Understanding Agent ────────────────────────────────────────────────

class TestQueryUnderstandingAgent:

    def test_english_query(self):
        mock_response = json.dumps({
            "detected_language": "english",
            "normalized_query": "Am I eligible for ATKT examination?",
            "intent": "atkt_form_eligibility",
            "entities": {"exam_type": "ATKT"}
        })
        with patch("agents.query_understanding_agent.get_llm") as mock_llm:
            mock_llm.return_value.invoke.return_value = MagicMock(content=mock_response)
            from agents.query_understanding_agent import query_understanding_agent
            state = _base_state(raw_query="Am I eligible for ATKT?")
            result = query_understanding_agent(state)

        assert result["detected_language"] == Language.ENGLISH
        assert result["intent"] == "atkt_form_eligibility"
        assert result["normalized_query"] == "Am I eligible for ATKT examination?"

    def test_gujarati_query(self):
        mock_response = json.dumps({
            "detected_language": "gujarati",
            "normalized_query": "I want to fill the ATKT form. Am I eligible?",
            "intent": "atkt_form_eligibility",
            "entities": {}
        })
        with patch("agents.query_understanding_agent.get_llm") as mock_llm:
            mock_llm.return_value.invoke.return_value = MagicMock(content=mock_response)
            from agents.query_understanding_agent import query_understanding_agent
            state = _base_state(raw_query="ATKT form bharva eligible chhu ke nahi?")
            result = query_understanding_agent(state)

        assert result["detected_language"] == Language.GUJARATI
        assert "atkt" in result["intent"].lower()

    def test_malformed_json_graceful(self):
        with patch("agents.query_understanding_agent.get_llm") as mock_llm:
            mock_llm.return_value.invoke.return_value = MagicMock(content="not json at all")
            from agents.query_understanding_agent import query_understanding_agent
            state = _base_state(raw_query="hello")
            result = query_understanding_agent(state)

        assert result["detected_language"] == Language.UNKNOWN
        assert len(result["errors"]) > 0


# ── Policy Agent ─────────────────────────────────────────────────────────────

class TestPolicyAgent:

    def test_no_index_returns_graceful_error(self):
        with patch("agents.policy_agent.get_vectorstore", return_value=None):
            from agents.policy_agent import policy_agent
            state = _base_state(
                normalized_query="Am I eligible for ATKT?",
                raw_query="ATKT eligibility?"
            )
            result = policy_agent(state)

        assert result["retrieved_policies"] == []
        assert "not yet initialized" in result["policy_summary"]
        assert len(result["errors"]) > 0

    def test_with_mock_vectorstore(self):
        mock_doc = MagicMock()
        mock_doc.page_content = "Students with fewer than 4 backlogs are eligible for ATKT."
        mock_doc.metadata = {"source": "exam_rules.txt", "department": "exam"}

        mock_vs = MagicMock()
        mock_vs.similarity_search_with_score.return_value = [(mock_doc, 0.2)]

        mock_summary = "Students with fewer than 4 backlogs may apply for ATKT."

        with patch("agents.policy_agent.get_vectorstore", return_value=mock_vs), \
             patch("agents.policy_agent.get_llm") as mock_llm:
            mock_llm.return_value.invoke.return_value = MagicMock(content=mock_summary)
            from agents.policy_agent import policy_agent
            state = _base_state(
                normalized_query="Am I eligible for ATKT?",
                raw_query="ATKT eligibility?"
            )
            result = policy_agent(state)

        assert len(result["retrieved_policies"]) == 1
        assert result["retrieved_policies"][0]["source"] == "exam_rules.txt"
        assert result["policy_summary"] == mock_summary


# ── Decision Agent ────────────────────────────────────────────────────────────

class TestDecisionAgent:

    def test_allowed_decision(self):
        mock_response = json.dumps({
            "outcome": "allowed",
            "reasoning": "Student has fewer than 4 backlogs per exam_rules.txt",
            "policy_references": ["exam_rules.txt"],
            "confidence": 0.9,
            "conditions": None
        })
        with patch("agents.decision_agent.get_llm") as mock_llm:
            mock_llm.return_value.invoke.return_value = MagicMock(content=mock_response)
            from agents.decision_agent import decision_agent
            state = _base_state(
                normalized_query="Am I eligible for ATKT?",
                entities={"backlogs": "2"},
                policy_summary="Students with fewer than 4 backlogs are eligible.",
                retrieved_policies=[{"source": "exam_rules.txt", "content": "...", "department": "exam", "score": 0.9}]
            )
            result = decision_agent(state)

        assert result["decision"]["outcome"] == DecisionOutcome.ALLOWED
        assert result["decision"]["confidence"] == 0.9

    def test_not_allowed_decision(self):
        mock_response = json.dumps({
            "outcome": "not_allowed",
            "reasoning": "Student has 5 backlogs which exceeds the maximum of 4.",
            "policy_references": ["exam_rules.txt"],
            "confidence": 0.95,
            "conditions": None
        })
        with patch("agents.decision_agent.get_llm") as mock_llm:
            mock_llm.return_value.invoke.return_value = MagicMock(content=mock_response)
            from agents.decision_agent import decision_agent
            state = _base_state(
                normalized_query="Can I fill ATKT form with 5 backlogs?",
                entities={"backlogs": "5"},
                policy_summary="Students with 5 or more backlogs are NOT eligible.",
                retrieved_policies=[]
            )
            result = decision_agent(state)

        assert result["decision"]["outcome"] == DecisionOutcome.NOT_ALLOWED


# ── Supervisor Agent ──────────────────────────────────────────────────────────

class TestSupervisorAgent:

    def test_approves_valid_decision(self):
        mock_response = json.dumps({
            "approved": True,
            "feedback": "OK",
            "severity": "low"
        })
        with patch("agents.supervisor_agent.get_llm") as mock_llm:
            mock_llm.return_value.invoke.return_value = MagicMock(content=mock_response)
            from agents.supervisor_agent import supervisor_agent
            from state import DecisionRecord, DecisionOutcome
            state = _base_state(
                raw_query="ATKT eligibility?",
                policy_summary="Students with fewer than 4 backlogs are eligible.",
                decision=DecisionRecord(
                    outcome=DecisionOutcome.ALLOWED,
                    reasoning="Has only 2 backlogs.",
                    policy_references=["exam_rules.txt"],
                    confidence=0.9,
                    conditions=None,
                ),
                final_response="Yes, you are eligible to fill the ATKT form.",
            )
            result = supervisor_agent(state)

        assert result["supervisor_approved"] is True
        assert result["supervisor_feedback"] == "OK"

    def test_rejects_low_confidence(self):
        mock_response = json.dumps({
            "approved": False,
            "feedback": "Confidence too low to make an 'allowed' decision.",
            "severity": "high"
        })
        with patch("agents.supervisor_agent.get_llm") as mock_llm:
            mock_llm.return_value.invoke.return_value = MagicMock(content=mock_response)
            from agents.supervisor_agent import supervisor_agent
            from state import DecisionRecord, DecisionOutcome
            state = _base_state(
                raw_query="some query",
                policy_summary="No relevant policy found.",
                decision=DecisionRecord(
                    outcome=DecisionOutcome.ALLOWED,
                    reasoning="Assumed allowed.",
                    policy_references=[],
                    confidence=0.3,
                    conditions=None,
                ),
                final_response="You are allowed.",
            )
            result = supervisor_agent(state)

        assert result["supervisor_approved"] is False
        assert result["retry_count"] == 1

    def test_force_approve_after_max_retries(self):
        from agents.supervisor_agent import supervisor_agent
        from state import DecisionRecord, DecisionOutcome
        state = _base_state(
            raw_query="query",
            policy_summary="policy",
            decision=DecisionRecord(
                outcome=DecisionOutcome.CONDITIONAL,
                reasoning="reason",
                policy_references=[],
                confidence=0.5,
                conditions=None,
            ),
            final_response="response",
            retry_count=999,
        )
        result = supervisor_agent(state)
        assert result["supervisor_approved"] is True


# ── Conditional edge ──────────────────────────────────────────────────────────

class TestShouldRollback:
    def test_approved_returns_approved(self):
        from agents.supervisor_agent import should_rollback
        state = _base_state(supervisor_approved=True, retry_count=0)
        assert should_rollback(state) == "approved"

    def test_rejected_returns_rollback(self):
        from agents.supervisor_agent import should_rollback
        state = _base_state(supervisor_approved=False, retry_count=0)
        assert should_rollback(state) == "rollback"

    def test_max_retries_forces_approved(self):
        from agents.supervisor_agent import should_rollback
        state = _base_state(supervisor_approved=False, retry_count=999)
        assert should_rollback(state) == "approved"
