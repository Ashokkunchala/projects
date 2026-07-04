"""Free tier routes — info, summary, check, usage, AI insights."""

import json as _json

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from main import (
    _FREE_TIER_AVAILABLE,
    _free_tier,
    _free_tier_usage,
    _DEBUG,
    _reconstruct_resources_from_analysis,
    _verify_token,
    db,
)
from cloudflare_ai import (
    free_tier_recommendations,
    free_tier_eligibility_check,
)

router = APIRouter(prefix="")


class FreeTierRecommendationsRequest(BaseModel):
    usage_data: dict = Field(default_factory=dict)
    provider: str = "aws"


class FreeTierEligibilityAIRequest(BaseModel):
    resource_types: list[str] = Field(default_factory=list)
    provider: str = "aws"


@router.get("/api/free-tier")
async def get_free_tier(provider: str = Query("all", pattern="^(all|aws|azure|gcp)$")):
    if not _FREE_TIER_AVAILABLE:
        return {"error": "Free tier module not available"}
    return _free_tier.get_free_tier(provider)


@router.get("/api/free-tier/summary")
async def get_free_tier_summary(provider: str = Query("all", pattern="^(all|aws|azure|gcp)$")):
    if not _FREE_TIER_AVAILABLE:
        return {"error": "Free tier module not available"}
    return {"services": _free_tier.get_free_tier_summary(provider)}


@router.get("/api/free-tier/check")
async def check_free_tier_eligibility(
    provider: str = Query("aws", pattern="^(aws|azure|gcp)$"),
    resources: str = Query("[]", description="JSON array of resource types"),
):
    if not _FREE_TIER_AVAILABLE:
        return {"error": "Free tier module not available"}
    try:
        resource_list = _json.loads(resources)
        return _free_tier.check_free_tier_eligibility(provider, resource_list)
    except _json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid resources JSON")


@router.get("/api/free-tier/usage/{provider}")
async def get_free_tier_usage(provider: str, user_info: dict = Depends(_verify_token)):
    try:
        import free_tier_usage as _ft_usage
    except ImportError:
        return {"error": "Free tier usage module not available"}

    analyses = await db.get_analyses_by_user(user_info["user_id"], limit=1)
    if not analyses:
        return {"error": "No scan results found. Run a scan first."}

    latest = analyses[0]
    result = latest.get("analysis_result") or latest.get("resources_scanned", 0)

    resources = {}
    if isinstance(result, dict):
        resources = _reconstruct_resources_from_analysis(result, provider)

    return _ft_usage.get_free_tier_usage(provider, resources)


@router.post("/api/free-tier/recommendations", include_in_schema=_DEBUG)
async def free_tier_recommendations_endpoint(req: FreeTierRecommendationsRequest, user_info: dict = Depends(_verify_token)):
    recs = await free_tier_recommendations(req.usage_data, req.provider)
    return {"recommendations": recs or []}


@router.post("/api/free-tier/check/ai", include_in_schema=_DEBUG)
async def free_tier_check_ai(req: FreeTierEligibilityAIRequest, user_info: dict = Depends(_verify_token)):
    result = await free_tier_eligibility_check(req.resource_types, req.provider)
    return result or {"error": "AI eligibility check unavailable"}
