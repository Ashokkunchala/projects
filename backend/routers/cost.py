"""Cost routes — explorer, forecast, variation, rightsizing, awareness, AI insights."""

import asyncio
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from main import (
    CostExplorerRequest,
    _DEBUG,
    _verify_token,
)
from cloudflare_ai import (
    cost_spike_explanation,
    forecast_narrative,
    rightsizing_explanation,
    personalized_awareness,
)

router = APIRouter(prefix="")


class ExplainRequest(BaseModel):
    service_totals: dict = Field(default_factory=dict)
    total_spend: float = 0.0
    changes: dict = Field(default_factory=dict)


class ForecastNarrativeRequest(BaseModel):
    forecasts: list[dict] = Field(default_factory=list)
    current_total: float = 0.0


class RightsizingExplainRequest(BaseModel):
    recommendation: dict = Field(default_factory=dict)


class PersonalizedAwarenessRequest(BaseModel):
    active_services: list[str] = Field(default_factory=list)


@router.post("/api/cost/explorer", include_in_schema=_DEBUG)
async def cost_explorer(req: CostExplorerRequest, user_info: dict = Depends(_verify_token)):
    import cost_explorer as _ce
    data = await asyncio.get_running_loop().run_in_executor(
        None,
        lambda: _ce.get_cost_data(
            access_key=req.aws_access_key_id or "",
            secret_key=req.aws_secret_access_key or "",
            session_token=req.aws_session_token or "",
            days=req.days,
        ),
    )
    return data


@router.post("/api/cost/forecast", include_in_schema=_DEBUG)
async def cost_forecast(req: CostExplorerRequest, user_info: dict = Depends(_verify_token)):
    import cost_explorer as _ce
    data = await asyncio.get_running_loop().run_in_executor(
        None,
        lambda: _ce.get_cost_forecast(
            access_key=req.aws_access_key_id or "",
            secret_key=req.aws_secret_access_key or "",
            session_token=req.aws_session_token or "",
        ),
    )
    return data


@router.get("/api/cost/awareness", include_in_schema=_DEBUG)
async def cost_awareness(
    category: Optional[str] = Query(default=None),
    limit: int = Query(default=10, ge=1, le=50),
    _: dict = Depends(_verify_token),
):
    import cost_awareness as _ca
    return _ca.get_awareness_items(category=category, limit=limit)


@router.post("/api/cost/variation", include_in_schema=_DEBUG)
async def cost_variation(req: CostExplorerRequest, user_info: dict = Depends(_verify_token)):
    import cost_explorer as _ce
    data = await asyncio.get_running_loop().run_in_executor(
        None,
        lambda: _ce.get_cost_variation(
            access_key=req.aws_access_key_id or "",
            secret_key=req.aws_secret_access_key or "",
            session_token=req.aws_session_token or "",
        ),
    )
    return data


@router.post("/api/cost/rightsizing", include_in_schema=_DEBUG)
async def cost_rightsizing(req: CostExplorerRequest, user_info: dict = Depends(_verify_token)):
    import cost_explorer as _ce
    recs = await asyncio.get_running_loop().run_in_executor(
        None,
        lambda: _ce.get_rightsizing_recommendations(
            access_key=req.aws_access_key_id or "",
            secret_key=req.aws_secret_access_key or "",
            session_token=req.aws_session_token or "",
        ),
    )
    return {"recommendations": recs}


@router.post("/api/cost/explain", include_in_schema=_DEBUG)
async def cost_explain(req: ExplainRequest, user_info: dict = Depends(_verify_token)):
    explanation = await cost_spike_explanation(req.service_totals, req.total_spend, req.changes)
    return {"explanation": explanation or "AI explanation unavailable"}


@router.post("/api/cost/forecast/narrative", include_in_schema=_DEBUG)
async def cost_forecast_narrative(req: ForecastNarrativeRequest, user_info: dict = Depends(_verify_token)):
    narrative = await forecast_narrative(req.forecasts, req.current_total)
    return {"narrative": narrative or "AI narrative unavailable"}


@router.post("/api/cost/rightsizing/explain", include_in_schema=_DEBUG)
async def cost_rightsizing_explain(req: RightsizingExplainRequest, user_info: dict = Depends(_verify_token)):
    explanation = await rightsizing_explanation(req.recommendation)
    return {"explanation": explanation or "AI explanation unavailable"}


@router.post("/api/cost/awareness/personalized", include_in_schema=_DEBUG)
async def cost_awareness_personalized(req: PersonalizedAwarenessRequest, user_info: dict = Depends(_verify_token)):
    tips = await personalized_awareness(req.active_services)
    return {"tips": tips or []}
