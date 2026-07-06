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
CF_ACCOUNT_ID = os.getenv("CLOUDFLARE_ACCOUNT_ID", "")
CF_API_TOKEN = os.getenv("CLOUDFLARE_API_TOKEN", "")
CF_DIRECT_API = bool(CF_ACCOUNT_ID and CF_API_TOKEN)  # direct API without a Worker
CF_FREE_MODEL = "@cf/meta/llama-3.1-8b-instruct-fp8"
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
    that benefit from stronger paid models (Anthropic Claude).
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


_PROVIDER_CONFIG = [
    ("google", "GOOGLE_API_KEY", "gemini-2.0-flash"),
    ("openai", "OPENAI_API_KEY", "gpt-4o"),
    ("anthropic", "ANTHROPIC_API_KEY", "claude-sonnet-4-6"),
    ("groq", "GROQ_API_KEY", "llama-3.3-70b-versatile"),
    ("deepseek", "DEEPSEEK_API_KEY", "deepseek-chat"),
    ("xai", "XAI_API_KEY", "grok-2-1212"),
    ("mistral", "MISTRAL_API_KEY", "mistral-large-latest"),
    ("cohere", "COHERE_API_KEY", "command-r-plus"),
    ("together", "TOGETHER_API_KEY", "mistralai/Mixtral-8x7B-Instruct-v0.1"),
    ("perplexity", "PERPLEXITY_API_KEY", "sonar-pro"),
    ("bedrock", None, None),
    ("ollama", None, None),
]


def _has_paid_provider() -> bool:
    """Check if any paid AI provider is configured on the backend."""
    for name, env_key, _ in _PROVIDER_CONFIG:
        if name == "bedrock":
            if os.getenv("BEDROCK_REGION", "").strip():
                return True
            continue
        if name == "ollama":
            if os.getenv("OLLAMA_BASE_URL", "").strip():
                return True
            continue
        if env_key and os.getenv(env_key, "").strip():
            return True
    return False


def _get_best_provider() -> str | None:
    """Return the name of the best configured paid provider, or None."""
    for name, env_key, _ in _PROVIDER_CONFIG:
        if name == "bedrock":
            if os.getenv("BEDROCK_REGION", "").strip():
                return name
            continue
        if name == "ollama":
            if os.getenv("OLLAMA_BASE_URL", "").strip():
                return name
            continue
        if env_key and os.getenv(env_key, "").strip():
            return name
    return None


async def routed_chat(
    messages: list[dict],
    context: dict | None = None,
    backend_user_id: int = 0,
    conversation_id: int | None = None,
    force_provider: str | None = None,
) -> str | None:
    """Route a chat request to the appropriate model based on query complexity.

    - Simple queries: Cloudflare Worker (free, Llama 3.1 8B)
    - Complex queries + any paid provider: use best available
    - Complex queries + no paid provider: Cloudflare Worker (still works, less optimal)

    force_provider: 'cloudflare', 'paid', or specific provider name to override.
    """
    last_user_msg = ""
    for m in reversed(messages):
        if m.get("role") == "user":
            last_user_msg = m.get("content", "")
            break

    if force_provider and force_provider not in ("cloudflare", "paid", "auto"):
        provider = force_provider
    elif force_provider == "cloudflare":
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
    elif provider != "cloudflare":
        return await _paid_chat_provider(messages, context, provider)
    else:
        return await chat_completion(messages, context, backend_user_id, conversation_id)


async def _paid_chat(messages: list[dict], context: dict | None = None) -> str | None:
    """Route chat to the best available paid provider, else fall back to Cloudflare."""
    provider = _get_best_provider()
    if provider:
        result = await _paid_chat_provider(messages, context, provider)
        if result is not None:
            return result
        logger.warning("ai.paid_fallback", extra={"provider": provider, "reason": "returned None, using cloudflare"})

    return await chat_completion(messages, context)


async def _paid_chat_provider(messages: list[dict], context: dict | None = None, provider_name: str = "anthropic") -> str | None:
    """Route chat to a specific paid provider by name."""
    system_msg = _build_system_for_paid(context)
    api_messages = [{"role": m["role"], "content": m["content"]} for m in messages if m["role"] != "system"]

    if provider_name == "anthropic":
        api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
        if api_key:
            return await _call_anthropic(messages, api_key, context)
    elif provider_name == "google" or provider_name == "gemini":
        api_key = os.getenv("GOOGLE_API_KEY", "") or os.getenv("GEMINI_API_KEY", "")
        if api_key:
            return await _call_google(api_messages, api_key, system_msg, context)
    elif provider_name == "openai" or provider_name == "groq" or provider_name == "deepseek" or provider_name == "xai" or provider_name == "mistral" or provider_name == "cohere" or provider_name == "together" or provider_name == "perplexity":
        api_key = os.getenv(f"{provider_name.upper()}_API_KEY", "").strip()
        base_urls = {
            "openai": "https://api.openai.com/v1",
            "groq": "https://api.groq.com/openai/v1",
            "deepseek": "https://api.deepseek.com/v1",
            "xai": "https://api.x.ai/v1",
            "mistral": "https://api.mistral.ai/v1",
            "cohere": "https://api.cohere.ai/v1",
            "together": "https://api.together.xyz/v1",
            "perplexity": "https://api.perplexity.ai",
        }
        if api_key and provider_name in base_urls:
            return await _call_openai_compat(api_messages, api_key, base_urls[provider_name], system_msg, provider_name)
    elif provider_name == "azure":
        api_key = os.getenv("AZURE_OPENAI_API_KEY", "").strip()
        endpoint = os.getenv("AZURE_OPENAI_ENDPOINT", "").strip()
        if api_key and endpoint:
            return await _call_openai_compat(api_messages, api_key, f"{endpoint}/openai/deployments/{os.getenv('AI_MODEL', 'gpt-4o')}/chat/completions?api-version=2024-02-15-preview", system_msg, "azure")
    elif provider_name == "bedrock":
        return await _call_bedrock(api_messages, system_msg)
    elif provider_name == "ollama":
        return await _call_ollama(api_messages, system_msg)

    return None


async def _call_google(messages: list[dict], api_key: str, system: str = "", context: dict | None = None) -> str | None:
    """Call Google Gemini API."""
    try:
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        model_name = os.getenv("AI_MODEL", "gemini-2.0-flash")
        model = genai.GenerativeModel(model_name)
        user_content = "\n".join(m.get("content", "") for m in messages if m.get("role") == "user")
        prompt = f"{system}\n\n{user_content}" if system else user_content
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        logger.warning(f"google.call_failed", extra={"error": str(e)})
        return None


async def _call_openai_compat(messages: list[dict], api_key: str, base_url: str, system: str = "", provider: str = "openai") -> str | None:
    """Call any OpenAI-compatible API."""
    try:
        import openai as _openai
        model = os.getenv("AI_MODEL", _DEFAULT_MODELS.get(provider, "gpt-4o"))
        client = _openai.OpenAI(api_key=api_key, base_url=base_url)
        api_msgs = [{"role": "system", "content": system}] if system else []
        api_msgs.extend(messages)
        response = client.chat.completions.create(
            model=model,
            messages=api_msgs,
            max_tokens=2048,
            temperature=0.3,
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.warning(f"{provider}.call_failed", extra={"error": str(e)})
        return None


async def _call_bedrock(messages: list[dict], system: str = "") -> str | None:
    """Call AWS Bedrock."""
    try:
        import boto3 as _boto3
        import json as _json
        region = os.getenv("BEDROCK_REGION", "us-east-1")
        model_id = os.getenv("AI_MODEL", "anthropic.claude-3-sonnet-20240229-v1:0")
        client = _boto3.client("bedrock-runtime", region_name=region)
        user_content = "\n".join(m.get("content", "") for m in messages if m.get("role") == "user")
        prompt = f"{system}\n\n{user_content}" if system else user_content
        body = _json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 2048,
            "messages": [{"role": "user", "content": prompt}],
        })
        resp = client.invoke_model(modelId=model_id, contentType="application/json", accept="application/json", body=body)
        return _json.loads(resp["body"].read()).get("content", [{}])[0].get("text", "")
    except Exception as e:
        logger.warning("bedrock.call_failed", extra={"error": str(e)})
        return None


async def _call_ollama(messages: list[dict], system: str = "") -> str | None:
    """Call local Ollama instance."""
    try:
        import httpx as _httpx
        base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
        model = os.getenv("AI_MODEL", "llama3.2")
        prompt = "\n".join(m.get("content", "") for m in messages if m.get("role") == "user")
        full_prompt = f"{system}\n\n{prompt}" if system else prompt
        async with _httpx.AsyncClient(timeout=300) as client:
            resp = await client.post(
                f"{base_url}/api/chat",
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": full_prompt}],
                    "stream": False,
                },
            )
            resp.raise_for_status()
            return resp.json().get("message", {}).get("content", "")
    except Exception as e:
        logger.warning("ollama.call_failed", extra={"error": str(e)})
        return None


_DEFAULT_MODELS = {
    "openai": "gpt-4o",
    "groq": "llama-3.3-70b-versatile",
    "deepseek": "deepseek-chat",
    "xai": "grok-2-1212",
    "mistral": "mistral-large-latest",
    "cohere": "command-r-plus",
    "together": "mistralai/Mixtral-8x7B-Instruct-v0.1",
    "perplexity": "sonar-pro",
}


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

async def _call_direct_api(
    prompt: str,
    system: str = "",
    max_tokens: int = 2048,
    temperature: float = 0.3,
) -> str | None:
    """Call Cloudflare Workers AI directly via REST API (no Worker needed)."""
    if not CF_DIRECT_API:
        return None
    model = os.getenv("CLOUDFLARE_AI_MODEL", CF_FREE_MODEL)
    url = f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}/ai/run/{model}"
    headers = {"Authorization": f"Bearer {CF_API_TOKEN}", "Content-Type": "application/json"}
    messages = [{"role": "system", "content": system}] if system else []
    messages.append({"role": "user", "content": prompt})
    body = {"messages": messages, "max_tokens": max_tokens, "temperature": temperature}
    for attempt in range(_MAX_RETRIES):
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.post(url, json=body, headers=headers)
                resp.raise_for_status()
                data = resp.json()
                if data.get("success"):
                    result = data.get("result", {})
                    return result.get("response", "")
                logger.warning("cf_direct.api_not_success", extra={"errors": data.get("errors", [])})
        except Exception as e:
            if attempt < _MAX_RETRIES - 1:
                await asyncio.sleep(_RETRY_DELAYS[attempt])
            else:
                logger.warning("cf_direct.call_failed", extra={"error": str(e)})
    return None


async def _call_worker(
    prompt: str,
    system: str = "",
    max_tokens: int = 2048,
    temperature: float = 0.3,
) -> str | None:
    """Send a prompt to the Cloudflare Worker's complete endpoint with retry logic.
    Falls back to direct Cloudflare API if no Worker URL is configured but
    Cloudflare API credentials are available.
    """
    if WORKER_URL:
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
    return await _call_direct_api(prompt, system, max_tokens, temperature)


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

    # If /chat endpoint not found (old Worker), fall back to /complete or direct API
    if result is None:
        prompt = f"{last_user_msg}"
        if conv_summary:
            prompt = f"Conversation so far:{conv_summary}\n\nUser's latest message: {last_user_msg}"

        if WORKER_URL:
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
        elif CF_DIRECT_API:
            return await _call_direct_api(
                prompt,
                system_msg or "You are the AI Cost Detective — an expert cloud infrastructure advisor. Be concise and actionable.",
                max_tokens, temperature,
            )

    return result.get("response") if result else None


async def chat_stream(
    messages: list[dict],
    context: dict | None = None,
    backend_user_id: int = 0,
    conversation_id: int | None = None,
    max_tokens: int = 2048,
    temperature: float = 0.3,
):
    """Stream chat responses from the Worker via SSE, or fall back to direct API."""
    # Build prompt for fallback
    last_user_msg = ""
    conv_summary = ""
    for m in reversed(messages):
        if m.get("role") == "user":
            last_user_msg = m.get("content", "")
            break
    for m in messages[-5:]:
        role = "User" if m.get("role") == "user" else "Assistant"
        conv_summary += f"\n{role}: {m.get('content', '')[:500]}"

    system_msg = ""
    if context:
        if context.get("page") == "/report":
            system_msg = "You are the AI Cost Detective assistant. The user is viewing a scan report."
        elif context.get("analysis_result"):
            result = context["analysis_result"]
            system_msg = f"Scan context: {result.get('total_resources', 0)} resources, {result.get('issues_found', 0)} issues, ${result.get('estimated_monthly_savings', 0)}/month savings potential."

    if WORKER_URL:
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
    elif CF_DIRECT_API:
        prompt = last_user_msg
        if conv_summary:
            prompt = f"Conversation so far:{conv_summary}\n\nUser's latest message: {last_user_msg}"
        result = await _call_direct_api(
            prompt,
            system_msg or "You are the AI Cost Detective — an expert cloud infrastructure advisor. Be concise and actionable.",
            max_tokens, temperature,
        )
        if result:
            yield result
        else:
            yield "\n[Direct Cloudflare API unavailable]"


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
