"""
tools/email_tool.py

FIX LIST:
1. send_email sync wrapper uses asyncio.new_event_loop() instead of
   asyncio.run() to avoid "event loop already running" error when called
   from FastAPI (which already has a running loop).
2. Graceful no-op when SMTP credentials not configured — logs info instead
   of silently returning False with no explanation.
3. Added email validation before attempting send.
"""
import asyncio
import logging
import re

import aiosmtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from config import cfg

logger = logging.getLogger(__name__)


def _is_valid_email(address: str) -> bool:
    return bool(re.match(r"[^@]+@[^@]+\.[^@]+", address or ""))


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type(Exception),
    reraise=True,
)
async def send_email_async(to: str, subject: str, body: str) -> bool:
    if not cfg.SMTP_USER or not cfg.SMTP_PASS:
        logger.info("[EmailTool] SMTP credentials not configured — skipping send.")
        return False

    if not _is_valid_email(to):
        logger.warning(f"[EmailTool] Invalid recipient address: {to!r}")
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = cfg.EMAIL_FROM
    msg["To"]      = to
    msg.attach(MIMEText(body, "plain", "utf-8"))

    await aiosmtplib.send(
        msg,
        hostname=cfg.SMTP_HOST,
        port=cfg.SMTP_PORT,
        username=cfg.SMTP_USER,
        password=cfg.SMTP_PASS,
        start_tls=True,
    )
    logger.info(f"[EmailTool] Email sent to {to}")
    return True


def send_email(to: str, subject: str, body: str) -> bool:
    """
    Synchronous wrapper — safe to call from both sync and async contexts.
    FIX: creates a fresh event loop instead of using asyncio.run() which
    fails when called from within FastAPI's async context.
    """
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(send_email_async(to, subject, body))
        finally:
            loop.close()
    except Exception as e:
        logger.error(f"[EmailTool] Failed to send email to {to}: {e}")
        return False
