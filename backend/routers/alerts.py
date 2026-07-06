"""Alert routes — configure notification channels and view alert history."""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from main import _verify_token, _check_rate_limit, db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/alerts")


class AlertConfigRequest(BaseModel):
    email: Optional[str] = Field(default=None, max_length=254)
    slack_webhook: Optional[str] = Field(default=None, max_length=1000)
    notify_on: list[str] = Field(default=["anomaly", "budget", "scan_complete"], max_length=10)


@router.get("/config")
async def get_alert_config(user_info: dict = Depends(_verify_token)):
    """Get the current user's alert configuration."""
    config = await db.get_alert_config(user_info["user_id"])
    if not config:
        return {"email": None, "slack_webhook": None, "notify_on": ["anomaly"]}
    return config


@router.put("/config")
async def update_alert_config(req: AlertConfigRequest, user_info: dict = Depends(_verify_token)):
    """Update alert configuration."""
    await _check_rate_limit(f"alerts:config:{user_info['user_id']}", max_attempts=10, window_seconds=60)
    config = await db.set_alert_config(user_info["user_id"], req.model_dump())
    return config


@router.post("/test")
async def test_alert(user_info: dict = Depends(_verify_token)):
    """Send a test notification to verify configuration."""
    from notifications import send_cost_alert
    user = await db.get_user_by_id(user_info["user_id"])
    email = user.get("email") if user else None
    await send_cost_alert(
        alert_type="test",
        title="Test Notification",
        message="This is a test alert from Cloud Cost Detective. Your notification channels are working correctly.",
        severity="low",
        user_email=email,
    )
    return {"status": "test notification sent"}


@router.get("/history")
async def get_alert_history(
    limit: int = Query(default=50, ge=1, le=200),
    user_info: dict = Depends(_verify_token),
):
    """Get alert history for the current user."""
    history = await db.get_alert_history(user_info["user_id"], limit=limit)
    return {"history": history}
