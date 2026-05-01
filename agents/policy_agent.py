
import os
import re
import logging
import threading
from typing import List

from langchain_core.messages import HumanMessage, SystemMessage
from config import cfg
from llm_factory import get_llm, safe_invoke
from state import AgentState, PolicyChunk

logger = logging.getLogger(__name__)

# ── Optional imports with graceful fallback ───────────────────────────────────
try:
    from langchain_huggingface import HuggingFaceEmbeddings
except ImportError:
    from langchain_community.embeddings import HuggingFaceEmbeddings  # type: ignore

try:
    from pinecone import Pinecone, ServerlessSpec
    from langchain_pinecone import PineconeVectorStore
    PINECONE_OK = True
except ImportError:
    PINECONE_OK = False
    logger.warning("pinecone-client / langchain-pinecone not installed – vector search disabled")

# ── Module-level singletons ────────────────────────────────────────────────────
_vectorstore = None
_embeddings  = None
_lock        = threading.Lock()

SUMMARY_PROMPT = """You are a college policy analyst.
Given retrieved policy excerpts and a student query, write a concise policy summary (3-5 sentences)
covering ONLY the rules relevant to this query.
Do NOT add information absent from the excerpts.
Output plain text only – no markdown, no bullet points."""

# ── BM25 keyword re-ranker ────────────────────────────────────────────────────
def _bm25_rerank(query: str, chunks: List[PolicyChunk], top_k: int = 5) -> List[PolicyChunk]:
    """
    Simple keyword overlap re-ranking (no extra dep).
    Boosts chunks that share words with the query.
    """
    q_words = set(re.sub(r"[^a-z0-9\s]", "", query.lower()).split())
    scored = []
    for chunk in chunks:
        c_words = set(re.sub(r"[^a-z0-9\s]", "", chunk["content"].lower()).split())
        overlap  = len(q_words & c_words)
        # Hybrid score: 70% semantic + 30% BM25-style keyword overlap
        bm25_score = overlap / (len(q_words) + 1)
        hybrid     = 0.7 * chunk["score"] + 0.3 * bm25_score
        scored.append((hybrid, chunk))
    scored.sort(key=lambda x: x[0], reverse=True)
    result = [c for _, c in scored[:top_k]]
    for i, chunk in enumerate(result):
        chunk["score"] = round(scored[i][0], 4)
    return result


# ── Embedding singleton ────────────────────────────────────────────────────────
def _get_embeddings() -> HuggingFaceEmbeddings:
    global _embeddings
    if _embeddings is None:
        _embeddings = HuggingFaceEmbeddings(
            model_name=cfg.EMBEDDING_MODEL,
            model_kwargs={"device": "cpu"},
            encode_kwargs={"normalize_embeddings": True},
        )
    return _embeddings


# ── Vectorstore loader ─────────────────────────────────────────────────────────
def get_vectorstore():
    global _vectorstore
    if _vectorstore is not None:
        return _vectorstore

    with _lock:
        if _vectorstore is not None:
            return _vectorstore

        if not PINECONE_OK:
            logger.error("Pinecone packages not installed.")
            return None

        if not cfg.PINECONE_API_KEY:
            logger.error("PINECONE_API_KEY not set in environment.")
            return None

        try:
            pc = Pinecone(api_key=cfg.PINECONE_API_KEY)

            # Create index if it doesn't exist (dim=384 for all-MiniLM-L6-v2)
            existing = [idx.name for idx in pc.list_indexes()]
            if cfg.PINECONE_INDEX not in existing:
                logger.info(f"Pinecone index '{cfg.PINECONE_INDEX}' not found. Creating...")
                pc.create_index(
                    name=cfg.PINECONE_INDEX,
                    dimension=384,
                    metric="cosine",
                    spec=ServerlessSpec(cloud="aws", region="us-east-1"),
                )
                logger.info(f"Pinecone index '{cfg.PINECONE_INDEX}' created.")

            _vectorstore = PineconeVectorStore(
                index_name=cfg.PINECONE_INDEX,
                embedding=_get_embeddings(),
                pinecone_api_key=cfg.PINECONE_API_KEY,
            )
            logger.info(f"Pinecone vectorstore loaded (index: {cfg.PINECONE_INDEX})")
        except Exception as e:
            logger.error(f"Failed to connect to Pinecone: {e}")
            return None

    return _vectorstore


# ── Agent node ────────────────────────────────────────────────────────────────
def policy_agent(state: AgentState) -> AgentState:
    """LangGraph node: retrieve relevant policy chunks (hybrid) and summarise."""
    query = state.get("normalized_query") or state["raw_query"]
    vs    = get_vectorstore()

    retrieved: List[PolicyChunk] = []

    if vs is None:
        no_index_summary = (
            "Policy database not yet initialised. "
            "Set PINECONE_API_KEY and run:  python tools/ingest_policies.py  then restart the server."
        )
        return {
            **state,
            "retrieved_policies": [],
            "policy_summary":     no_index_summary,
            "errors": state.get("errors", []) + ["PolicyAgent: Pinecone vectorstore unavailable."],
        }

    # ── Pinecone semantic search ──────────────────────────────────────────────
    try:
        docs_with_scores = vs.similarity_search_with_score(query, k=8)
        for doc, score in docs_with_scores:
            # Pinecone cosine score is already 0-1 (higher = more similar)
            retrieved.append(
                PolicyChunk(
                    content=doc.page_content,
                    source=doc.metadata.get("source", "unknown"),
                    department=doc.metadata.get("department", "general"),
                    score=round(float(score), 4),
                )
            )
    except Exception as e:
        logger.error(f"PolicyAgent Pinecone retrieval error: {e}")
        return {
            **state,
            "retrieved_policies": [],
            "policy_summary":     "Could not retrieve policies due to an internal error.",
            "errors": state.get("errors", []) + [f"PolicyAgent retrieval error: {e}"],
        }

    # ── Hybrid re-rank (semantic + keyword) ───────────────────────────────────
    if retrieved:
        retrieved = _bm25_rerank(query, retrieved, top_k=5)

    # ── LLM policy summary ────────────────────────────────────────────────────
    llm = get_llm(temperature=0.0, fast=False)
    excerpts = "\n\n".join(
        f"[{p['source']} | {p['department']} | score:{p['score']}]\n{p['content']}"
        for p in retrieved
    )
    messages = [
        SystemMessage(content=SUMMARY_PROMPT),
        HumanMessage(content=f"Student query: {query}\n\nPolicy excerpts:\n{excerpts}"),
    ]

    try:
        policy_summary = safe_invoke(llm, messages, context="PolicyAgent-summary")
    except Exception as e:
        logger.warning(f"PolicyAgent summary LLM failed, using raw excerpts: {e}")
        policy_summary = excerpts[:1200]

    return {
        **state,
        "retrieved_policies": retrieved,
        "policy_summary":     policy_summary,
    }
