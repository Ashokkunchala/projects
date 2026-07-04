"""Cloudflare Worker AI agent proxy — forwards requests to the Cloudflare Worker.

Includes chat, conversation management, and streaming support.
"""

import asyncio
import json as _json
import logging
import os

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from main import _verify_token
from cloudflare_ai import routed_chat

logger = logging.getLogger(__name__)

WORKER_URL = os.getenv("CLOUDFLARE_WORKER_URL", "")
TIMEOUT = 60.0

router = APIRouter(prefix="/api/agent")


# ─── Request Models ─────────────────────────────────────────────────────────

class ChatMessage(BaseModel):
    role: str = Field(..., pattern=r'^(user|assistant|system)$')
    content: str = Field(..., min_length=1, max_length=10000)


class ChatContext(BaseModel):
    analysis_id: str | None = None
    analysis_result: dict | None = None
    scan_data: dict | None = None
    page: str | None = None
    user_services: list[str] | None = None


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(..., min_length=1)
    context: ChatContext | None = None
    conversation_id: int | None = None
    max_tokens: int = Field(default=2048, ge=100, le=4096)
    temperature: float = Field(default=0.3, ge=0.0, le=1.0)


class ConversationCreate(BaseModel):
    title: str = Field(default="New conversation", max_length=200)


class FixRequest(BaseModel):
    issue: dict = Field(..., description="Issue object from scan results")
    context: dict | None = None


class CostSimulateRequest(BaseModel):
    resource: dict = Field(..., description="Resource object from scan results")
    proposed_change: str = Field(..., min_length=5, max_length=500)


class ComplianceCheckRequest(BaseModel):
    resources: dict = Field(..., description="Resources to check")
    framework: str = Field(default="cis", pattern=r"^(cis|soc2|pci|hipaa|iso27001)$")


class AnomalyDetectRequest(BaseModel):
    current_scan: dict = Field(..., description="Current scan result")
    historical_scans: list[dict] = Field(default_factory=list, description="Previous scan results")


class IaCGenerateRequest(BaseModel):
    description: str = Field(..., min_length=10, max_length=2000)
    format: str = Field(default="terraform", pattern=r"^(terraform|cloudformation)$")
    provider: str = Field(default="aws", pattern=r"^(aws|azure|gcp)$")


class ResourceLookupRequest(BaseModel):
    query: str = Field(..., min_length=3, max_length=500, description="Natural language query about resources")


# ─── Chat Endpoint ──────────────────────────────────────────────────────────

@router.post("/chat")
async def agent_chat(req: ChatRequest, request: Request, user_info: dict = Depends(_verify_token)):
    """Send a chat message to the AI Agent. Uses model router for optimal provider selection."""
    user_id = user_info["user_id"]

    messages = [m.model_dump() for m in req.messages]
    context = req.context.model_dump() if req.context else None

    response = await routed_chat(
        messages=messages,
        context=context,
        backend_user_id=user_id,
        conversation_id=req.conversation_id,
    )

    if response is None:
        raise HTTPException(502, "AI Agent unavailable")

    return {"response": response, "conversation_id": req.conversation_id}


@router.post("/chat/stream")
async def agent_chat_stream(req: ChatRequest, request: Request, user_info: dict = Depends(_verify_token)):
    """Stream chat responses from the AI Agent via SSE."""
    user_id = user_info["user_id"]

    payload = {
        "messages": [m.model_dump() for m in req.messages],
        "context": req.context.model_dump() if req.context else None,
        "backend_user_id": user_id,
        "max_tokens": req.max_tokens,
        "temperature": req.temperature,
        "stream": True,
    }
    if req.conversation_id:
        payload["conversation_id"] = req.conversation_id

    async def event_generator():
        import httpx
        headers = {"Content-Type": "application/json", "Accept": "text/event-stream", "X-Backend-User-Id": str(user_id)}
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                async with client.stream("POST", f"{WORKER_URL}/api/agent/chat", json=payload, headers=headers) as resp:
                    resp.raise_for_status()
                    async for line in resp.aiter_lines():
                        if line.startswith("data: "):
                            yield line + "\n\n"
                            if line.strip().endswith("[DONE]"):
                                break
        except httpx.TimeoutException:
            yield f"data: {_json.dumps({'error': 'Agent timed out'})}\n\n"
        except Exception as e:
            yield f"data: {_json.dumps({'error': str(e)})}\n\n"
            yield "data: [DONE]\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# ─── Conversation CRUD ──────────────────────────────────────────────────────

@router.get("/conversations")
async def list_conversations(user_info: dict = Depends(_verify_token)):
    """List chat conversations for the current user."""
    user_id = user_info["user_id"]
    try:
        import httpx
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{WORKER_URL}/api/agent/conversations",
                params={"user_id": user_id},
            )
            resp.raise_for_status()
            return resp.json()
    except Exception as e:
        logger.error(f"agent.conversations error: {e}")
        return {"conversations": []}


@router.post("/conversations")
async def create_conversation(req: ConversationCreate, user_info: dict = Depends(_verify_token)):
    """Create a new chat conversation."""
    user_id = user_info["user_id"]
    try:
        import httpx
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{WORKER_URL}/api/agent/conversations",
                json={"title": req.title, "backend_user_id": user_id},
                headers={"X-Backend-User-Id": str(user_id)},
            )
            resp.raise_for_status()
            return resp.json()
    except Exception as e:
        logger.error(f"agent.create_conversation error: {e}")
        raise HTTPException(502, "Failed to create conversation")


@router.get("/conversations/{conversation_id}")
async def get_conversation_messages(conversation_id: int, user_info: dict = Depends(_verify_token)):
    """Get messages for a specific conversation."""
    try:
        import httpx
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{WORKER_URL}/api/agent/conversations/{conversation_id}")
            resp.raise_for_status()
            return resp.json()
    except Exception as e:
        logger.error(f"agent.get_messages error: {e}")
        return {"messages": []}


@router.delete("/conversations/{conversation_id}")
async def delete_conversation(conversation_id: int, user_info: dict = Depends(_verify_token)):
    """Delete a conversation and its messages."""
    try:
        import httpx
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.delete(f"{WORKER_URL}/api/agent/conversations/{conversation_id}")
            resp.raise_for_status()
            return resp.json()
    except Exception as e:
        logger.error(f"agent.delete_conversation error: {e}")
        raise HTTPException(502, "Failed to delete conversation")


# ─── Existing Proxy Endpoints ───────────────────────────────────────────────

@router.post("/analyze")
async def agent_analyze(req: dict, user_info: dict = Depends(_verify_token)):
    import httpx
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        try:
            resp = await client.post(f"{WORKER_URL}/api/agent/analyze", json=req)
            resp.raise_for_status()
            return resp.json()
        except httpx.TimeoutException:
            raise HTTPException(504, "Cloudflare Worker timed out")
        except httpx.HTTPStatusError as e:
            raise HTTPException(e.response.status_code, detail="Worker request failed")
        except httpx.RequestError:
            raise HTTPException(502, "Cannot reach Cloudflare Worker")


@router.post("/validate")
async def agent_validate(req: dict, user_info: dict = Depends(_verify_token)):
    import httpx
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        try:
            resp = await client.post(f"{WORKER_URL}/api/agent/validate", json=req)
            resp.raise_for_status()
            return resp.json()
        except httpx.TimeoutException:
            raise HTTPException(504, "Cloudflare Worker timed out")
        except httpx.HTTPStatusError as e:
            raise HTTPException(e.response.status_code, detail="Worker request failed")
        except httpx.RequestError:
            raise HTTPException(502, "Cannot reach Cloudflare Worker")


@router.post("/explain")
async def agent_explain(req: dict, user_info: dict = Depends(_verify_token)):
    import httpx
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        try:
            resp = await client.post(f"{WORKER_URL}/api/agent/explain", json=req)
            resp.raise_for_status()
            return resp.json()
        except httpx.TimeoutException:
            raise HTTPException(504, "Cloudflare Worker timed out")
        except httpx.HTTPStatusError as e:
            raise HTTPException(e.response.status_code, detail="Worker request failed")
        except httpx.RequestError:
            raise HTTPException(502, "Cannot reach Cloudflare Worker")


@router.post("/complete")
async def agent_complete(req: dict, user_info: dict = Depends(_verify_token)):
    import httpx
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        try:
            resp = await client.post(f"{WORKER_URL}/api/agent/complete", json=req)
            resp.raise_for_status()
            return resp.json()
        except httpx.TimeoutException:
            raise HTTPException(504, "Cloudflare Worker timed out")
        except httpx.HTTPStatusError as e:
            raise HTTPException(e.response.status_code, detail="Worker request failed")
        except httpx.RequestError:
            raise HTTPException(502, "Cannot reach Cloudflare Worker")


@router.get("/health")
async def agent_health():
    import httpx
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.get(f"{WORKER_URL}/api/agent/health")
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.error(f"agent.health error: {e}")
            raise HTTPException(502, "Worker health check failed")


# ─── Advanced Agent Capabilities (Phase 5) ─────────────────────────────────

@router.post("/fix")
async def generate_fix(req: FixRequest, user_info: dict = Depends(_verify_token)):
    """Generate a complete, production-ready fix command for a specific issue."""
    from cloudflare_ai import generate_fix as _gen_fix
    result = await _gen_fix(req.issue, req.context)
    return result or {"error": "Could not generate fix"}


@router.post("/simulate")
async def simulate_cost_change(req: CostSimulateRequest, user_info: dict = Depends(_verify_token)):
    """Simulate the cost impact of a proposed infrastructure change."""
    from cloudflare_ai import simulate_cost_change as _sim
    result = await _sim(req.resource, req.proposed_change)
    return result or {"error": "Could not simulate cost change"}


@router.post("/compliance")
async def compliance_check(req: ComplianceCheckRequest, user_info: dict = Depends(_verify_token)):
    """Check infrastructure resources against a compliance framework."""
    from cloudflare_ai import compliance_check as _compliance
    result = await _compliance(req.resources, req.framework)
    return result or {"error": "Could not run compliance check"}


@router.post("/anomalies")
async def detect_anomalies(req: AnomalyDetectRequest, user_info: dict = Depends(_verify_token)):
    """Detect anomalies by comparing current scan with historical data."""
    from cloudflare_ai import detect_anomalies as _anomalies
    result = await _anomalies(req.current_scan, req.historical_scans)
    return {"anomalies": result or []}


@router.post("/generate-iac")
async def generate_iac(req: IaCGenerateRequest, user_info: dict = Depends(_verify_token)):
    """Generate Infrastructure as Code from a natural language description."""
    from cloudflare_ai import generate_iac as _gen_iac
    result = await _gen_iac(req.description, req.format, req.provider)
    return result or {"error": "Could not generate IaC"}


@router.post("/resource-lookup")
async def resource_lookup(req: ResourceLookupRequest, user_info: dict = Depends(_verify_token)):
    """Look up resources using natural language queries against scan data."""
    # Get the user's latest scan
    analyses = await db.get_analyses_by_user(user_info["user_id"], limit=1)
    if not analyses:
        return {"error": "No scan results found. Run a scan first."}

    latest = analyses[0]
    result = latest.get("analysis_result")
    if not result:
        return {"error": "No analysis result available."}

    # Use the Agent to interpret the query against the scan data
    issues = result.get("issues", [])
    resources_summary = json.dumps({
        "total_resources": result.get("total_resources", 0),
        "issues": [{"service": i.get("service"), "resource": i.get("resource_name"),
                    "severity": i.get("severity"), "type": i.get("issue_type"),
                    "savings": i.get("potential_monthly_savings")} for i in issues[:50]],
        "total_savings": result.get("estimated_monthly_savings", 0),
    }, indent=2)

    messages = [{
        "role": "user",
        "content": f"Based on this scan data, answer the user's question.\n\nScan data:\n{resources_summary}\n\nUser question: {req.query}\n\nProvide a concise answer with specific resource names and numbers. If relevant, list the matching resources."
    }]

    response = await routed_chat(messages, context={"page": "/resource-lookup"}, backend_user_id=user_info["user_id"])
    return {"response": response or "Could not process the query"}
