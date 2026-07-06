"""Notification service — email, Slack, webhook alerts.

Uses Cloudflare Email Routing API or SMTP for email,
and generic webhooks for Slack/Discord notifications.

Configure via environment variables:
  NOTIFICATIONS_ENABLED=true
  SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS  (for email)
  NOTIFICATION_FROM_EMAIL=alerts@yourdomain.com
  SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...
  WEBHOOK_URL=https://...  (generic fallback)
"""

import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

_ENABLED = os.getenv("NOTIFICATIONS_ENABLED", "false").lower() == "true"

# ─── Email via SMTP ────────────────────────────────────────────────────────

_SMTP_HOST = os.getenv("SMTP_HOST", "")
_SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
_SMTP_USER = os.getenv("SMTP_USER", "")
_SMTP_PASS = os.getenv("SMTP_PASS", "")
_FROM_EMAIL = os.getenv("NOTIFICATION_FROM_EMAIL", "alerts@costdetective.dev")

# ─── Slack / Webhook ───────────────────────────────────────────────────────

_SLACK_WEBHOOK = os.getenv("SLACK_WEBHOOK_URL", "")
_WEBHOOK_URL = os.getenv("WEBHOOK_URL", "")


async def send_email(to: str, subject: str, body_text: str, body_html: Optional[str] = None) -> bool:
    if not _ENABLED or not _SMTP_HOST:
        if not _ENABLED:
            logger.info("notifications.email.disabled — set NOTIFICATIONS_ENABLED=true and SMTP_HOST/SMTP_USER/SMTP_PASS")
        elif not _SMTP_HOST:
            logger.info("notifications.email.disabled — set SMTP_HOST (e.g. smtp.gmail.com)")
        return False
    cf_token = os.getenv("CLOUDFLARE_API_TOKEN", "")
    cf_zone = os.getenv("CLOUDFLARE_ZONE_ID", "")
    if cf_token and cf_zone and os.getenv("CLOUDFLARE_WORKER_URL", ""):
        return await _send_via_cloudflare(to, subject, body_text, body_html, cf_token, cf_zone)
    return await _send_via_smtp(to, subject, body_text, body_html)


async def send_slack(message: str, title: Optional[str] = None) -> bool:
    """Send a Slack notification via webhook."""
    if not _ENABLED or not _SLACK_WEBHOOK:
        logger.info("notifications.slack.disabled")
        return False
    try:
        payload = {"text": f"*{title or 'Cloud Cost Detective'}*\n{message}"}
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(_SLACK_WEBHOOK, json=payload)
            resp.raise_for_status()
            logger.info("notifications.slack.sent", extra={"title": title})
            return True
    except Exception as e:
        logger.warning("notifications.slack.failed", extra={"error": str(e)})
        return False


async def send_webhook(payload: dict) -> bool:
    """Send a generic webhook notification."""
    if not _ENABLED or not _WEBHOOK_URL:
        return False
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(_WEBHOOK_URL, json=payload)
            resp.raise_for_status()
            return True
    except Exception as e:
        logger.warning("notifications.webhook.failed", extra={"error": str(e)})
        return False


async def send_cost_alert(
    alert_type: str,
    title: str,
    message: str,
    severity: str = "medium",
    user_email: Optional[str] = None,
) -> None:
    """Send a cost-related alert through all configured channels."""
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    full_msg = f"[{severity.upper()}] {message}\n\n{title} — {timestamp}"

    tasks = []
    if user_email:
        tasks.append(send_email(user_email, f"[Cost Detective] {title}", full_msg))
    tasks.append(send_slack(full_msg, title))
    tasks.append(send_webhook({"type": alert_type, "title": title, "message": message, "severity": severity, "timestamp": timestamp}))
    await asyncio.gather(*tasks)


# ─── Internal helpers ──────────────────────────────────────────────────────

async def _send_via_cloudflare(to: str, subject: str, body_text: str, body_html: Optional[str], token: str, zone: str) -> bool:
    """Send email via Cloudflare Workers AI + MailChannels (requires a worker deployed at CLOUDFLARE_WORKER_URL)."""
    worker_url = os.getenv("CLOUDFLARE_WORKER_URL", "")
    if not worker_url:
        logger.warning("notifications.cloudflare.no_worker — set CLOUDFLARE_WORKER_URL to a MailChannels worker endpoint, falling back to SMTP")
        return await _send_via_smtp(to, subject, body_text, body_html)
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                worker_url.rstrip("/") + "/send-email",
                headers={"Authorization": f"Bearer {token}"},
                json={"to": to, "subject": subject, "text": body_text, "html": body_html},
            )
            if resp.status_code < 400:
                logger.info("notifications.cloudflare.email.sent", extra={"to": to})
                return True
            logger.warning("notifications.cloudflare.email.failed", extra={"status": resp.status_code, "body": resp.text})
            return False
    except Exception as e:
        logger.warning("notifications.cloudflare.email.error", extra={"error": str(e)})
        return False


async def _send_via_smtp(to: str, subject: str, body_text: str, body_html: Optional[str] = None) -> bool:
    """Send email via SMTP with HTML fallback."""
    import smtplib
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = _FROM_EMAIL
        msg["To"] = to
        msg.attach(MIMEText(body_text, "plain"))
        if body_html:
            msg.attach(MIMEText(body_html, "html"))
        with smtplib.SMTP(_SMTP_HOST, _SMTP_PORT) as server:
            server.starttls()
            server.login(_SMTP_USER, _SMTP_PASS)
            server.send_message(msg)
        logger.info("notifications.smtp.sent", extra={"to": to, "subject": subject})
        return True
    except Exception as e:
        logger.warning("notifications.smtp.failed", extra={"error": str(e)})
        return False
