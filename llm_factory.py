
import logging
from functools import lru_cache
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
)
from langchain_groq import ChatGroq
from config import cfg

logger = logging.getLogger(__name__)


def get_llm(temperature: float = 0.1, fast: bool = False) -> ChatGroq:
    """
    Return a ChatGroq instance.
    fast=True  → uses LLM_MODEL_FAST (llama-3.1-8b-instant) for speed/cost
    fast=False → uses LLM_MODEL (llama-3.3-70b-versatile) for quality
    """
    if not cfg.GROQ_API_KEY:
        raise ValueError(
            "GROQ_API_KEY is not set. Please add it to your .env file.\n"
            "Get a free key at: https://console.groq.com"
        )
    model = cfg.LLM_MODEL_FAST if fast else cfg.LLM_MODEL
    return ChatGroq(
        model=model,
        temperature=temperature,
        groq_api_key=cfg.GROQ_API_KEY,
        # FIX: cap max_tokens to avoid hitting context-length errors
        max_tokens=1024,
        # FIX: add request timeout so the pipeline never hangs forever
        request_timeout=60,
    )


def safe_invoke(llm: ChatGroq, messages: list, context: str = "") -> str:
    """
    Invoke the LLM with automatic retry on transient errors.
    Returns the content string. Raises on permanent failure.
    FIX: centralised retry wrapper used by all agents so they don't
         each re-implement error handling.
    """
    import httpx
    from groq import RateLimitError, APIStatusError

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=15),
        retry=retry_if_exception_type((RateLimitError, httpx.TimeoutException, ConnectionError)),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )
    def _call():
        return llm.invoke(messages)

    try:
        resp = _call()
        return resp.content.strip()
    except Exception as exc:
        logger.error(f"LLM call failed [{context}]: {exc}")
        raise
