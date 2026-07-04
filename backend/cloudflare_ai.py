"""Shared Cloudflare Workers AI utility — powers AI features across all services.

All functions are async with retry logic (3 attempts, exponential backoff).
Chat functions support streaming via SSE.
"""

import asyncio
import json
import logging
import os
import re
from typing import Any

import httpx

logger = logging.getLogger(__name__)

WORKER_URL = os.getenv("CLOUDFLARE_WORKER_URL", "")
_TIMEOUT = 120.0
_MAX_RETRIES = 3
_RETRY_DELAYS = [0.5, 1.0, 2.0]

# ─── Model Router ──────────────────────────────────────────────────────────

# Complex query indicators
_COMPLEX_KEYWORDS = {
    "compare", "architecture", "generate", "terraform", "cloudformation",
    "compliance", "audit", "simulate", "forecast", "multi-account",
    "cross-region", "migration", "disaster recovery", "ha", "high availability",
    "security audit", "penetration", "vulnerability", "cis benchmark",
}

# Simple query indicators
_SIMPLE_KEYWORDS = {
    "explain", "what is", "help", "how to", "why", "define", "meaning",
    "hello", "hi", "thanks", "yes", "no",
}


def classify_query_complexity(query: str) -> str:
    """Classify a query as 'simple' or 'complex' based on content analysis.

    Returns 'simple' for basic questions that can be handled by Cloudflare's free Llama 3.1 8B.
    Returns 'complex' for multi-step analysis, code generation, or compliance checks
    that benefit from stronger paid models (Claude/GPT-4o).
    """
    query_lower = query.lower()

    # Check for complex indicators
    complex_score = sum(1 for kw in _COMPLEX_KEYWORDS if kw in query_lower)
    simple_score = sum(1 for kw in _SIMPLE_KEYWORDS if kw in query_lower)

    # Long queries with technical content tend to be complex
    word_count = len(query.split())
    if word_count > 100:
        complex_score += 2

    # JSON payloads with multiple resources suggest analysis
    if query.count('{') > 5 or query.count('"type"') > 3:
        complex_score += 2

    if complex_score > simple_score and complex_score >= 2:
        return "complex"
    return "simple"


def _has_paid_provider() -> bool:
    """Check if any paid AI provider is configured on the backend."""
    paid_keys = [
        "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GOOGLE_API_KEY",
        "GEMINI_API_KEY", "GROQ_API_KEY", "DEEPSEEK_API_KEY",
    ]
    return any(os.getenv(k, "").strip() for k in paid_keys)


async def routed_chat(
    messages: list[dict],
    context: dict | None = None,
    backend_user_id: int = 0,
    conversation_id: int | None = None,
    force_provider: str | None = None,
) -> str | None:
    """Route a chat request to the appropriate model based on query complexity.

    - Simple queries: Cloudflare Worker (free, Llama 3.1 8B)
    - Complex queries + paid provider available: Claude/GPT-4o (better reasoning)
    - Complex queries + no paid provider: Cloudflare Worker (still works, less optimal)

    force_provider: 'cloudflare' or 'paid' to override auto-routing.
    """
    last_user_msg = ""
    for m in reversed(messages):
        if m.get("role") == "user":
            last_user_msg = m.get("content", "")
            break

    if force_provider == "cloudflare":
        provider = "cloudflare"
    elif force_provider == "paid":
        provider = "paid" if _has_paid_provider() else "cloudflare"
    else:
        complexity = classify_query_complexity(last_user_msg)
        if complexity == "complex" and _has_paid_provider():
            provider = "paid"
        else:
            provider = "cloudflare"

    logger.info("ai.router", extra={"provider": provider, "query_length": len(last_user_msg)})

    if provider == "paid":
        return await _paid_chat(messages, context)
    else:
        return await chat_completion(messages, context, backend_user_id, conversation_id)


async def _paid_chat(messages: list[dict], context: dict | None = None) -> str | None:
    """Route chat to the best available paid AI provider."""
    # Try providers in order of quality
    providers = [
        ("ANTHROPIC_API_KEY", "anthropic"),
        ("OPENAI_API_KEY", "openai"),
        ("GOOGLE_API_KEY", "google"),
        ("GROQ_API_KEY", "groq"),
        ("DEEPSEEK_API_KEY", "deepseek"),
    ]

    for env_key, provider_name in providers:
        api_key = os.getenv(env_key, "").strip()
        if not api_key:
            continue

        try:
            if provider_name == "anthropic":
                return await _call_anthropic(messages, api_key, context)
            elif provider_name == "openai":
                return await _call_openai(messages, api_key, context)
            elif provider_name == "google":
                return await _call_google(messages, api_key, context)
            # Groq and DeepSeek use OpenAI-compatible API
            elif provider_name in ("groq", "deepseek"):
                base_url = "https://api.groq.com/openai/v1" if provider_name == "groq" else "https://api.deepseek.com/v1"
                return await _call_openai_compat(messages, api_key, context, base_url)
        except Exception as e:
            logger.warning("ai.paid_provider_failed", extra={"provider": provider_name, "error": str(e)})
            continue

    # Fallback to Cloudflare
    return await chat_completion(messages, context)


async def _call_anthropic(messages: list[dict], api_key: str, context: dict | None = None) -> str | None:
    """Call Anthropic Claude API."""
    system_msg = _build_system_for_paid(context)
    api_messages = [{"role": m["role"], "content": m["content"]} for m in messages if m["role"] != "system"]

    payload = {
        "model": "claude-sonnet-4-20250514",
        "max_tokens": 2048,
        "system": system_msg,
        "messages": api_messages,
    }

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(
                "https://api.anthropic.com/v1/messages",
                json=payload,
                headers={"x-api-key": api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("content", [{}])[0].get("text", "")
    except Exception as e:
        logger.warning("anthropic.call_failed", extra={"error": str(e)})
        return None


async def _call_openai(messages: list[dict], api_key: str, context: dict | None = None) -> str | None:
    """Call OpenAI API."""
    return await _call_openai_compat(messages, api_key, context, "https://api.openai.com/v1")


async def _call_google(messages: list[dict], api_key: str, context: dict | None = None) -> str | None:
    """Call Google Gemini API."""
    system_msg = _build_system_for_paid(context)
    contents = []
    for m in messages:
        if m["role"] == "system":
            contents.append({"role": "user", "parts": [{"text": m["content"]}]})
            contents.append({"role": "model", "parts": [{"text": "Understood."}]})
        else:
            role = "user" if m["role"] == "user" else "model"
            contents.append({"role": role, "parts": [{"text": m["content"]}]})

    payload = {
        "contents": contents,
        "systemInstruction": {"parts": [{"text": system_msg}]},
        "generationConfig": {"maxOutputTokens": 2048, "temperature": 0.3},
    }

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}",
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
    except Exception as e:
        logger.warning("google.call_failed", extra={"error": str(e)})
        return None


async def _call_openai_compat(messages: list[dict], api_key: str, context: dict | None = None, base_url: str = "https://api.openai.com/v1") -> str | None:
    """Call OpenAI-compatible API (OpenAI, Groq, DeepSeek, etc.)."""
    system_msg = _build_system_for_paid(context)
    api_messages = [{"role": "system", "content": system_msg}]
    for m in messages:
        if m["role"] != "system":
            api_messages.append({"role": m["role"], "content": m["content"]})

    payload = {
        "model": "gpt-4o",
        "messages": api_messages,
        "max_tokens": 2048,
        "temperature": 0.3,
    }

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(
                f"{base_url}/chat/completions",
                json=payload,
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("choices", [{}])[0].get("message", {}).get("content", "")
    except Exception as e:
        logger.warning("openai_compat.call_failed", extra={"base_url": base_url, "error": str(e)})
        return None


def _build_system_for_paid(context: dict | None = None) -> str:
    """Build a system prompt for paid AI providers."""
    system = """You are the AI Cost Detective — an expert cloud infrastructure architect and cost optimization advisor.

Key capabilities:
- Analyze cloud resources across AWS, Azure, and GCP
- Explain cost anomalies and provide savings recommendations
- Generate fix commands for infrastructure issues
- Help with Terraform/CloudFormation code
- Check compliance with security benchmarks

Response guidelines:
- Be concise and actionable. Focus on the most impactful advice first.
- Use specific numbers when discussing costs ($X/month savings).
- When suggesting fixes, provide the exact CLI command.
- Use markdown formatting: **bold** for emphasis, `code` for commands, and bullet points for lists."""

    if context:
        if context.get("page") == "/report":
            system += "\n\nThe user is viewing a scan report. Help them understand findings and prioritize fixes."
        elif context.get("analysis_result"):
            result = context["analysis_result"]
            issues = result.get("issues", [])
            high_issues = [i for i in issues if i.get("severity") in ("high", "critical")]
            system += f"\n\nCurrent scan: {result.get('total_resources', 0)} resources, {result.get('issues_found', 0)} issues, ${result.get('estimated_monthly_savings', 0)}/month savings potential."
            if high_issues:
                system += f"\nTop issues: {'; '.join(i.get('message', '') for i in high_issues[:5])}"

    return system


# ─── Async HTTP helpers ─────────────────────────────────────────────────────

async def _call_worker(
    prompt: str,
    system: str = "",
    max_tokens: int = 2048,
    temperature: float = 0.3,
) -> str | None:
    """Send a prompt to the Cloudflare Worker's complete endpoint with retry logic."""
    payload = {"prompt": prompt, "system": system, "max_tokens": max_tokens, "temperature": temperature}
    for attempt in range(_MAX_RETRIES):
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.post(f"{WORKER_URL}/api/agent/complete", json=payload)
                resp.raise_for_status()
                return resp.json().get("response", "")
        except Exception as e:
            if attempt < _MAX_RETRIES - 1:
                await asyncio.sleep(_RETRY_DELAYS[attempt])
            else:
                logger.warning("cf_ai.call_failed", extra={"error": str(e), "attempts": _MAX_RETRIES})
    return None


async def _call_worker_json(
    prompt: str,
    system: str = "",
    max_tokens: int = 2048,
    temperature: float = 0.3,
) -> list | dict | None:
    """Call the Worker and parse the response as JSON."""
    raw = await _call_worker(prompt, system, max_tokens, temperature)
    if raw:
        result = _extract_json(raw)
        if result:
            return result
        try:
            parsed = json.loads(raw)
            return parsed
        except json.JSONDecodeError:
            pass
    return None


async def _post_worker(path: str, payload: dict, backend_user_id: int = 0) -> dict | None:
    """Post to a Worker endpoint with retry logic."""
    headers = {"Content-Type": "application/json"}
    if backend_user_id:
        headers["X-Backend-User-Id"] = str(backend_user_id)
    for attempt in range(_MAX_RETRIES):
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.post(f"{WORKER_URL}{path}", json=payload, headers=headers)
                resp.raise_for_status()
                return resp.json()
        except Exception as e:
            if attempt < _MAX_RETRIES - 1:
                await asyncio.sleep(_RETRY_DELAYS[attempt])
            else:
                logger.warning("cf_ai.post_failed", extra={"path": path, "error": str(e)})
    return None


def _extract_json(text: str) -> dict | None:
    """Extract and parse the first JSON object from a text response."""
    match = re.search(r'\{[\s\S]*?\}', text)
    if not match:
        return None
    try:
        return json.loads(match.group())
    except json.JSONDecodeError:
        return None


# ─── Chat Functions ────────────────────────────────────────────────────────

async def chat_completion(
    messages: list[dict],
    context: dict | None = None,
    backend_user_id: int = 0,
    conversation_id: int | None = None,
    max_tokens: int = 2048,
    temperature: float = 0.3,
) -> str | None:
    """Send a chat completion request to the Worker and return the response text.

    Falls back to /api/agent/complete if the /chat endpoint is unavailable (404).
    """
    # Build the last user message into a prompt for the /complete fallback
    last_user_msg = ""
    for m in reversed(messages):
        if m.get("role") == "user":
            last_user_msg = m.get("content", "")
            break

    system_msg = ""
    if context:
        if context.get("page") == "/report":
            system_msg = "You are the AI Cost Detective assistant. The user is viewing a scan report."
        elif context.get("analysis_result"):
            result = context["analysis_result"]
            system_msg = f"Scan context: {result.get('total_resources', 0)} resources, {result.get('issues_found', 0)} issues, ${result.get('estimated_monthly_savings', 0)}/month savings potential."

    # Build conversation summary for the prompt
    conv_summary = ""
    for m in messages[-5:]:  # Last 5 messages for context
        role = "User" if m.get("role") == "user" else "Assistant"
        conv_summary += f"\n{role}: {m.get('content', '')[:500]}"

    payload = {
        "messages": messages,
        "context": context,
        "backend_user_id": backend_user_id,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    if conversation_id:
        payload["conversation_id"] = conversation_id

    result = await _post_worker("/api/agent/chat", payload, backend_user_id)

    # If /chat endpoint not found (old Worker), fall back to /complete
    if result is None:
        prompt = f"{last_user_msg}"
        if conv_summary:
            prompt = f"Conversation so far:{conv_summary}\n\nUser's latest message: {last_user_msg}"

        for attempt in range(_MAX_RETRIES):
            try:
                async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                    resp = await client.post(
                        f"{WORKER_URL}/api/agent/complete",
                        json={"prompt": prompt, "system": system_msg or "You are the AI Cost Detective — an expert cloud infrastructure advisor. Be concise and actionable.", "max_tokens": max_tokens, "temperature": temperature},
                    )
                    resp.raise_for_status()
                    return resp.json().get("response", "")
            except Exception as e:
                if attempt < _MAX_RETRIES - 1:
                    await asyncio.sleep(_RETRY_DELAYS[attempt])
                else:
                    logger.warning("cf_ai.complete_fallback_failed", extra={"error": str(e)})

    return result.get("response") if result else None


async def chat_stream(
    messages: list[dict],
    context: dict | None = None,
    backend_user_id: int = 0,
    conversation_id: int | None = None,
    max_tokens: int = 2048,
    temperature: float = 0.3,
):
    """Stream chat responses from the Worker via SSE. Yields tokens as they arrive."""
    payload = {
        "messages": messages,
        "context": context,
        "backend_user_id": backend_user_id,
        "stream": True,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    if conversation_id:
        payload["conversation_id"] = conversation_id

    headers = {"Content-Type": "application/json", "Accept": "text/event-stream"}
    if backend_user_id:
        headers["X-Backend-User-Id"] = str(backend_user_id)

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            async with client.stream("POST", f"{WORKER_URL}/api/agent/chat", json=payload, headers=headers) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if line.startswith("data: "):
                        data = line[6:]
                        if data == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data)
                            if "token" in chunk:
                                yield chunk["token"]
                            if "error" in chunk:
                                yield f"\n[Error: {chunk['error']}]"
                        except json.JSONDecodeError:
                            continue
    except Exception as e:
        logger.warning("cf_ai.stream_failed", extra={"error": str(e)})
        yield f"\n[Streaming error: {str(e)}]"


async def get_conversations(backend_user_id: int) -> list[dict]:
    """List conversations for a user."""
    result = await _post_worker("/api/agent/conversations", {"user_id": backend_user_id}, backend_user_id)
    return result.get("conversations", []) if result else []


async def get_conversation_messages(conversation_id: int) -> list[dict]:
    """Get messages for a conversation."""
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(f"{WORKER_URL}/api/agent/conversations/{conversation_id}")
            resp.raise_for_status()
            return resp.json().get("messages", [])
    except Exception as e:
        logger.warning("cf_ai.get_messages_failed", extra={"error": str(e)})
        return []


async def delete_conversation(conversation_id: int) -> bool:
    """Delete a conversation."""
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.delete(f"{WORKER_URL}/api/agent/conversations/{conversation_id}")
            resp.raise_for_status()
            return True
    except Exception as e:
        logger.warning("cf_ai.delete_conversation_failed", extra={"error": str(e)})
        return False


async def create_conversation(backend_user_id: int, title: str = "New conversation") -> dict | None:
    """Create a new conversation."""
    payload = {"title": title, "backend_user_id": backend_user_id}
    return await _post_worker("/api/agent/conversations", payload, backend_user_id)


# ─── Cost Insights (now async) ─────────────────────────────────────────────

async def cost_spike_explanation(service_totals: dict, total_spend: float, changes: dict) -> str | None:
    top = sorted(service_totals.items(), key=lambda x: -x[1])[:5]
    services_str = "\n".join(f"  {s}: ${c:.2f}" for s, c in top)
    changes_str = json.dumps(changes, indent=2) if changes else "none"
    prompt = f"""Analyze this AWS cost data and explain the key findings in 2-3 sentences:

Total spend: ${total_spend:.2f}
Top services:
{services_str}
Period-over-period changes:
{changes_str}

Provide a concise, actionable insight about cost trends and anomalies."""
    return await _call_worker(prompt, "You are an AWS cost optimization expert. Be concise and specific.", 256, 0.3)


async def forecast_narrative(forecasts: list[dict], current_total: float) -> str | None:
    forecast_lines = "\n".join(
        f"  {f['period']['Start']} to {f['period']['End']}: ${f['mean']:.2f}" for f in forecasts
    )
    prompt = f"""Current monthly spend: ${current_total:.2f}
Forecasted costs:
{forecast_lines}

Summarize this 90-day cost forecast in 1-2 sentences. Highlight trends and potential budget impacts."""
    return await _call_worker(prompt, "You are a financial analyst specializing in cloud costs. Be concise.", 256, 0.3)


async def rightsizing_explanation(recommendation: dict) -> str | None:
    prompt = f"""Explain this AWS rightsizing recommendation in one clear sentence:
- Resource: {recommendation.get('resource_id', 'unknown')}
- Current type: {recommendation.get('current_instance_type', 'unknown')}
- Recommended type: {recommendation.get('recommended_instance_type', 'unknown')}
- Monthly savings: ${recommendation.get('estimated_monthly_savings', 0):.2f}

Provide a concise, actionable explanation of why this change is recommended."""
    return await _call_worker(prompt, "You are an AWS optimization expert. One sentence only.", 128, 0.2)


async def personalized_awareness(active_services: list[str]) -> list[dict] | None:
    services_list = ", ".join(active_services) if active_services else "general AWS"
    prompt = f"""The user has these AWS services in use: {services_list}

Generate 3 specific, actionable cost-saving tips tailored to these services.
Each tip should have: category, title, summary (1 sentence), impact (savings estimate), action (what to do).

Return a JSON array of objects with keys: category, title, summary, impact, action."""
    return await _call_worker_json(prompt, "You are an AWS cost optimization expert. Return valid JSON array only.", 1024, 0.3)


# ─── Infra Visualizer Insights (now async) ─────────────────────────────────

async def infra_diagram_summary(nodes: list[dict], edges: list[dict]) -> str | None:
    node_summary = "\n".join(
        f"  {n.get('label', n.get('id', '?'))} ({n.get('type', n.get('service', '?'))})"
        for n in nodes[:20]
    )
    edge_summary = "\n".join(
        f"  {e.get('from', '?')} → {e.get('to', '?')} ({e.get('label', '')})"
        for e in edges[:20]
    )
    prompt = f"""Infrastructure resources ({len(nodes)} nodes, {len(edges)} connections):

Nodes:
{node_summary}

Connections:
{edge_summary}

Describe what this infrastructure does in 2-3 sentences. Focus on architecture patterns."""
    return await _call_worker(prompt, "You are a cloud solutions architect. Explain infrastructure clearly and concisely.", 256, 0.3)


async def infra_validation_analysis(raw_resources: dict) -> list[dict] | None:
    items = []
    for rid, res in raw_resources.items():
        items.append(f"  {rid}: {res.get('type', '?')} name={res.get('name', '')} config={json.dumps(res.get('config', {}))}")
    resource_block = "\n".join(items[:30])
    prompt = f"""Analyze these infrastructure resources for security risks, cost issues, and architecture anti-patterns:

{resource_block}

Return a JSON array of issues. Each issue must have: severity (critical|high|medium|low), category (security|cost|architecture|free_tier), resource_id, message (1 sentence), explanation, fix.

Output ONLY a valid JSON array."""
    return await _call_worker_json(prompt, "You are a cloud security and architecture expert. Return only valid JSON.", 2048, 0.2)


async def infra_cost_estimate(nodes: list[dict]) -> str | None:
    resource_lines = "\n".join(
        f"  {n.get('label', n.get('id', '?'))} ({n.get('type', n.get('service', '?'))})"
        for n in nodes[:20]
    )
    prompt = f"""Estimate the monthly cost of this infrastructure and suggest optimizations:
{resource_lines}

Provide a 2-3 sentence cost analysis."""
    return await _call_worker(prompt, "You are a cloud pricing expert. Be specific and actionable.", 256, 0.3)


# ─── Free Tier Insights (now async) ────────────────────────────────────────

async def free_tier_recommendations(usage_data: dict, provider: str) -> list[dict] | None:
    services_str = json.dumps(usage_data.get("services", {}), indent=2)[:2000]
    prompt = f"""Analyze this {provider} free tier usage data:

{services_str}

Generate 2-3 specific recommendations to stay within free tier limits or optimize usage.
Return a JSON array with each item having: title (short), description (1-2 sentences), action (what to do), impact (savings or benefit).

Output ONLY a valid JSON array."""
    return await _call_worker_json(
        prompt,
        f"You are a {provider} cloud expert specializing in free tier optimization. Return only valid JSON.",
        1024, 0.3,
    )


async def free_tier_eligibility_check(resource_types: list[str], provider: str) -> dict | None:
    types_str = ", ".join(resource_types)
    prompt = f"""Check if these {provider} resource types are eligible for free tier:
{types_str}

For each resource, provide: resource_type, eligible (true/false), limit (what the free tier covers), condition (if any), explanation.
Return a JSON object with: eligible (overall), services_checked (count), details (array with above fields).

Output ONLY valid JSON."""
    return await _call_worker_json(
        prompt,
        f"You are a {provider} cloud pricing expert with detailed free tier knowledge. Return only valid JSON.",
        1024, 0.2,
    )


# ─── Estimation Insights (now async) ───────────────────────────────────────

async def estimate_insights(resources_found: int, total_cost: float, service_breakdown: dict) -> str | None:
    top_services = sorted(service_breakdown.items(), key=lambda x: -x[1])[:5]
    services_str = "\n".join(f"  {s}: ${c:.2f}" for s, c in top_services)
    prompt = f"""Cost estimation results:
- Resources found: {resources_found}
- Total monthly cost: ${total_cost:.2f}
- Service breakdown:
{services_str}

Provide 2-3 cost optimization insights and recommendations based on this data."""
    return await _call_worker(prompt, "You are a cloud cost optimization expert. Be specific and actionable.", 512, 0.3)


# ─── Advanced Agent Functions (Phase 5) ────────────────────────────────────

async def generate_fix(issue: dict, context: dict | None = None) -> dict | None:
    """Generate a complete fix command for a specific issue."""
    ctx_str = ""
    if context:
        ctx_str = f"\nAdditional context: {json.dumps(context, indent=2)[:1000]}"
    prompt = f"""Generate a complete, production-ready fix for this cloud infrastructure issue:

Service: {issue.get('service', 'unknown')}
Resource: {issue.get('resource_name', 'unknown')} ({issue.get('resource_id', '')})
Region: {issue.get('region', '')}
Issue: {issue.get('explanation', issue.get('message', ''))}
Severity: {issue.get('severity', 'medium')}
{ctx_str}

Return a JSON object with:
{{
  "command": "the exact CLI command to run",
  "explanation": "1-2 sentence explanation of what the fix does",
  "prerequisites": ["list of prerequisites like IAM permissions needed"],
  "rollback": "command or steps to undo this change if needed",
  "impact": "what will change after applying this fix"
}}

Output ONLY valid JSON."""
    return await _call_worker_json(prompt, "You are a senior cloud infrastructure engineer. Return only valid JSON.", 1024, 0.2)


async def simulate_cost_change(resource: dict, proposed_change: str) -> dict | None:
    """Simulate the cost impact of a proposed infrastructure change."""
    prompt = f"""Simulate the cost impact of this infrastructure change:

Resource: {resource.get('name', 'unknown')} ({resource.get('type', 'unknown')})
Current config: {json.dumps(resource.get('config', {}), indent=2)[:500]}
Current instance type: {resource.get('instance_type', resource.get('node_type', 'unknown'))}
Region: {resource.get('region', 'us-east-1')}

Proposed change: {proposed_change}

Return a JSON object with:
{{
  "current_monthly_cost": 0.0,
  "new_monthly_cost": 0.0,
  "monthly_savings": 0.0,
  "annual_savings": 0.0,
  "risks": ["list of potential risks or tradeoffs"],
  "recommendation": "proceed | proceed_with_caution | not_recommended",
  "explanation": "1-2 sentence explanation"
}}

Output ONLY valid JSON."""
    return await _call_worker_json(prompt, "You are an AWS pricing expert. Be precise with numbers.", 1024, 0.2)


async def compliance_check(resources: dict, framework: str = "cis") -> dict | None:
    """Check infrastructure resources against a compliance framework."""
    resource_summary = json.dumps(resources, indent=2)[:3000]
    prompt = f"""Check these cloud resources against the {framework.upper()} compliance framework:

{resource_summary}

Return a JSON object with:
{{
  "framework": "{framework}",
  "score": 0-100,
  "passed_checks": 0,
  "total_checks": 0,
  "violations": [
    {{
      "control": "control ID",
      "severity": "critical|high|medium|low",
      "resource": "resource name",
      "description": "what's wrong",
      "fix": "how to fix"
    }}
  ],
  "recommendations": ["list of recommendations"]
}}

Output ONLY valid JSON."""
    return await _call_worker_json(prompt, f"You are a cloud compliance expert specializing in {framework.upper()} benchmarks. Return only valid JSON.", 2048, 0.2)


async def detect_anomalies(current_scan: dict, historical_scans: list[dict]) -> list[dict] | None:
    """Detect anomalies by comparing current scan with historical data."""
    current_summary = json.dumps({
        "resources": current_scan.get("total_resources", 0),
        "issues": current_scan.get("issues_found", 0),
        "savings": current_scan.get("estimated_monthly_savings", 0),
    })
    history_summary = json.dumps([{
        "date": s.get("created_at", ""),
        "resources": s.get("resources_scanned", 0),
        "issues": s.get("issues_found", 0),
        "savings": s.get("estimated_savings", ""),
    } for s in historical_scans[:10]])

    prompt = f"""Compare this scan with historical data and identify anomalies:

Current scan: {current_summary}

Previous scans: {history_summary}

Return a JSON array of anomalies. Each anomaly:
{{
  "type": "new_resources | removed_resources | cost_increase | cost_decrease | new_issues | resolved_issues",
  "severity": "high | medium | low",
  "message": "description of the anomaly",
  "details": "specific numbers or resource names",
  "recommendation": "what to do about it"
}}

Output ONLY a valid JSON array. If no anomalies, return an empty array."""
    return await _call_worker_json(prompt, "You are a cloud cost analyst. Identify significant changes between scans.", 1024, 0.2)


async def generate_iac(description: str, format: str = "terraform", provider: str = "aws") -> dict | None:
    """Generate Infrastructure as Code from a natural language description."""
    prompt = f"""Generate {format} code for the following infrastructure requirement:

Description: {description}
Provider: {provider}
Format: {format}

Return a JSON object with:
{{
  "code": "the generated {format} code",
  "format": "{format}",
  "explanation": "brief explanation of the resources created and their connections",
  "estimated_monthly_cost": 0.0,
  "warnings": ["any caveats or things to note"]
}}

Output ONLY valid JSON."""
    return await _call_worker_json(prompt, f"You are a senior {provider} cloud architect. Write production-ready {format} code with best practices. Return only valid JSON.", 4096, 0.2)
