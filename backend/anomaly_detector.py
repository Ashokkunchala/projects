"""Cost anomaly detector — analyzes scan history for cost anomalies.

Uses Cloudflare Workers AI for intelligent anomaly detection
and provides statistical baselines as fallback.
"""

import asyncio
import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

import db
from cloudflare_ai import detect_anomalies
from notifications import send_cost_alert

logger = logging.getLogger(__name__)

# How often to run the anomaly check (hours)
_CHECK_INTERVAL_HOURS = int(os.getenv("ANOMALY_CHECK_INTERVAL", "6"))

# Thresholds for statistical anomaly detection (fallback when AI is unavailable)
_COST_INCREASE_THRESHOLD_PCT = float(os.getenv("ANOMALY_COST_THRESHOLD_PCT", "20"))
_NEW_ISSUES_THRESHOLD = int(os.getenv("ANOMALY_ISSUES_THRESHOLD", "5"))


async def run_anomaly_check() -> list[dict]:
    """Run anomaly detection across all users with scan history.

    Returns a list of detected anomalies.
    """
    all_anomalies = []
    try:
        # Get all users who have scan history
        users = await _get_users_with_history()
        for user in users:
            anomalies = await _check_user_anomalies(user)
            all_anomalies.extend(anomalies)
    except Exception as e:
        logger.error("anomaly.check.error", extra={"error": str(e)})
    return all_anomalies


async def check_user_anomalies(user_id: int) -> list[dict]:
    """Check for anomalies in a single user's scan history."""
    return await _check_user_anomalies(user_id)


async def _check_user_anomalies(user_id: int) -> list[dict]:
    """Check a single user for cost anomalies."""
    anomalies = []
    try:
        analyses = await db.get_analyses_by_user(user_id, limit=20)
        if len(analyses) < 2:
            return anomalies  # Need at least 2 scans to compare

        # Get the two most recent completed analyses
        completed = [a for a in analyses if a.get("status") == "complete" and a.get("analysis_result")]
        if len(completed) < 2:
            return anomalies

        current = completed[0]
        previous = completed[1]

        current_result = current.get("analysis_result", {})
        previous_result = previous.get("analysis_result", {})

        # Statistical checks
        anomalies.extend(_statistical_checks(current_result, previous_result))

        # AI-powered anomaly detection
        historical_scans = [dict(a) for a in completed[1:6]]
        ai_anomalies = await detect_anomalies(current_result, historical_scans)
        if ai_anomalies:
            anomalies.extend(ai_anomalies)
            for anomaly in ai_anomalies:
                if anomaly.get("severity") in ("high", "critical"):
                    await send_cost_alert(
                        alert_type="cost_anomaly",
                        title=anomaly.get("message", "Cost Anomaly Detected"),
                        message=anomaly.get("details", ""),
                        severity=anomaly.get("severity", "medium"),
                    )

    except Exception as e:
        logger.warning("anomaly.user_check.error", extra={"user_id": user_id, "error": str(e)})

    return anomalies


def _statistical_checks(current: dict, previous: dict) -> list[dict]:
    """Simple statistical anomaly detection (fallback when AI is unavailable)."""
    anomalies = []

    curr_savings = current.get("estimated_monthly_savings", 0) or 0
    prev_savings = previous.get("estimated_monthly_savings", 0) or 0
    curr_issues = current.get("issues_found", 0) or 0
    prev_issues = previous.get("issues_found", 0) or 0
    curr_resources = current.get("total_resources", 0) or 0
    prev_resources = previous.get("total_resources", 0) or 0

    # Cost increase (savings decreased significantly)
    if prev_savings > 0 and curr_savings < prev_savings * (1 - _COST_INCREASE_THRESHOLD_PCT / 100):
        anomalies.append({
            "type": "cost_increase",
            "severity": "high",
            "message": "Potential cost increase detected",
            "details": f"Estimated savings dropped from ${prev_savings:.2f} to ${curr_savings:.2f}/month",
            "recommendation": "Review new resources and check for recent infrastructure changes",
        })

    # New issues appeared
    if curr_issues > prev_issues + _NEW_ISSUES_THRESHOLD:
        anomalies.append({
            "type": "new_issues",
            "severity": "medium",
            "message": f"{curr_issues - prev_issues} new cost issues detected",
            "details": f"Issues increased from {prev_issues} to {curr_issues}",
            "recommendation": "Review the new issues in the latest scan report",
        })

    # Resource count spike
    if prev_resources > 0 and curr_resources > prev_resources * 1.5:
        anomalies.append({
            "type": "new_resources",
            "severity": "medium",
            "message": f"Significant resource count increase: {curr_resources} vs {prev_resources}",
            "details": f"Resource count grew by {(curr_resources/prev_resources - 1)*100:.0f}%",
            "recommendation": "Verify new resources are expected and tagged appropriately",
        })

    return anomalies


async def _get_users_with_history() -> list[int]:
    """Get list of user IDs that have scan history."""
    try:
        # Query distinct user IDs from analyses
        if db.pool:
            async with db.pool.acquire() as conn:
                rows = await conn.fetch("SELECT DISTINCT user_id FROM analyses WHERE status = 'complete'")
                return [r["user_id"] for r in rows]
        return list(set(a.get("user_id", 0) for a in db._analyses_store.values() if a.get("status") == "complete"))
    except Exception:
        return []


async def anomaly_check_loop():
    """Background task: run anomaly checks periodically."""
    while True:
        try:
            logger.info("anomaly.check.starting")
            anomalies = await run_anomaly_check()
            logger.info("anomaly.check.complete", extra={"anomalies_found": len(anomalies)})
        except Exception as e:
            logger.error("anomaly.check.error", extra={"error": str(e)})
        await asyncio.sleep(_CHECK_INTERVAL_HOURS * 3600)
