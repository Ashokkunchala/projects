"""RI / Savings Plan recommendation routes."""

import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from main import (
    CostExplorerRequest,
    _DEBUG,
    _verify_token,
    _check_rate_limit,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/cost")


class RIRecommendation(BaseModel):
    service: str = "AmazonEC2"
    account_id: str = ""
    current_instance_type: str = ""
    recommended_plan: str = ""
    upfront: str = "partial"
    term: str = "1year"
    estimated_annual_savings: float = 0.0
    estimated_monthly_savings: float = 0.0
    coverage: float = 0.0
    explanation: str = ""


@router.post("/ri-recommendations", include_in_schema=_DEBUG)
async def get_ri_recommendations(req: CostExplorerRequest, user_info: dict = Depends(_verify_token)):
    """Get Reserved Instance and Savings Plan recommendations from AWS Cost Explorer."""
    try:
        import cost_explorer as _ce
        recs = await asyncio.get_running_loop().run_in_executor(
            None,
            lambda: _ce.get_ri_recommendations(
                access_key=req.aws_access_key_id or "",
                secret_key=req.aws_secret_access_key or "",
                session_token=req.aws_session_token or "",
            ),
        )
        return {"recommendations": recs}
    except ImportError:
        return {"error": "Cost Explorer module not available"}
    except Exception as e:
        logger.warning("ri.recommendations.error", extra={"error": str(e)})
        return {"recommendations": [], "error": str(e)}


@router.post("/savings-plans", include_in_schema=_DEBUG)
async def get_savings_plan_recommendations(req: CostExplorerRequest, user_info: dict = Depends(_verify_token)):
    """Get Savings Plan recommendations."""
    try:
        import cost_explorer as _ce
        recs = await asyncio.get_running_loop().run_in_executor(
            None,
            lambda: _ce.get_savings_plan_recommendations(
                access_key=req.aws_access_key_id or "",
                secret_key=req.aws_secret_access_key or "",
                session_token=req.aws_session_token or "",
            ),
        )
        return {"recommendations": recs}
    except ImportError:
        return {"error": "Cost Explorer module not available"}
    except Exception as e:
        logger.warning("savings_plans.recommendations.error", extra={"error": str(e)})
        return {"recommendations": [], "error": str(e)}
