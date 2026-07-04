"""Redis client for distributed state — rate limiting, SSO sessions, scan progress.

Enables horizontal scaling with multiple uvicorn workers (UVICORN_WORKERS > 1).
Gracefully degrades to in-memory fallback when Redis is unavailable.
"""

import asyncio
import json
import logging
import os
import time
from collections import defaultdict
from datetime import timedelta
from typing import Any, Optional

logger = logging.getLogger(__name__)

_redis = None
_pool = None
_fallback_mode = False

# In-memory fallback stores (used when Redis is unavailable)
_fallback_rate_buckets: dict[str, list] = defaultdict(list)
_fallback_rate_lock = asyncio.Lock()
_fallback_sso_sessions: dict[str, dict] = {}
_fallback_progress: dict[str, list] = {}
_fallback_progress_lock = asyncio.Lock()


async def init_redis():
    global _redis, _pool, _fallback_mode
    url = os.getenv("REDIS_URL", "redis://redis:6379/0")
    try:
        import redis.asyncio as aioredis
        _pool = aioredis.ConnectionPool.from_url(
            url,
            max_connections=20,
            socket_timeout=2,
            socket_connect_timeout=2,
            retry_on_timeout=True,
        )
        _redis = aioredis.Redis(connection_pool=_pool)
        await _redis.ping()
        logger.info("redis.connected", extra={"url": url.replace("://", "://...@") if "@" in url else url})
        _fallback_mode = False
    except Exception as e:
        logger.warning("redis.fallback", extra={"error": str(e), "detail": "running in-memory fallback mode"})
        _redis = None
        _pool = None
        _fallback_mode = True


async def close_redis():
    global _redis, _pool
    if _pool:
        await _pool.disconnect()
        _pool = None
        _redis = None


def _in_fallback() -> bool:
    return _fallback_mode or _redis is None


def is_fallback() -> bool:
    """Public check: True when Redis is unavailable and in-memory fallback is active."""
    return _fallback_mode or _redis is None


# ─── Rate Limiting ─────────────────────────────────────────────────────────────

async def rate_limit_check(key: str, max_attempts: int = 10, window_seconds: int = 60) -> bool:
    """Check rate limit. Returns True if allowed, False if rate-limited."""
    if not _in_fallback():
        try:
            pipe = _redis.pipeline()
            now = time.time()
            window_ms = int(window_seconds * 1000)
            pipe.zremrangebyscore(key, 0, now - window_seconds)
            pipe.zcard(key)
            pipe.zadd(key, {str(now): now})
            pipe.expire(key, window_seconds)
            results = await pipe.execute()
            count = results[1]
            return count < max_attempts
        except Exception:
            pass

    async with _fallback_rate_lock:
        now = time.time()
        _fallback_rate_buckets[key] = [t for t in _fallback_rate_buckets[key] if now - t < window_seconds]
        if len(_fallback_rate_buckets[key]) >= max_attempts:
            return False
        _fallback_rate_buckets[key].append(now)
        return True


# ─── SSO Sessions ──────────────────────────────────────────────────────────────

async def sso_session_set(session_id: str, data: dict) -> None:
    ttl = int(data.get("expires_at", time.time() + 3600) - time.time())
    ttl = max(ttl, 60)
    if not _in_fallback():
        try:
            await _redis.setex(f"sso:{session_id}", ttl, json.dumps(data))
            return
        except Exception:
            pass
    _fallback_sso_sessions[session_id] = data


async def sso_session_get(session_id: str) -> Optional[dict]:
    if not _in_fallback():
        try:
            raw = await _redis.get(f"sso:{session_id}")
            return json.loads(raw) if raw else None
        except Exception:
            pass
    return _fallback_sso_sessions.get(session_id)


async def sso_session_update(session_id: str, updates: dict) -> None:
    session = await sso_session_get(session_id)
    if session:
        session.update(updates)
        await sso_session_set(session_id, session)


async def sso_session_delete(session_id: str) -> None:
    if not _in_fallback():
        try:
            await _redis.delete(f"sso:{session_id}")
            return
        except Exception:
            pass
    _fallback_sso_sessions.pop(session_id, None)


# ─── Scan Progress ─────────────────────────────────────────────────────────────

async def progress_push(analysis_id: str, message: str, status: str = "in_progress", data: dict = None) -> None:
    entry = json.dumps({"message": message, "status": status, "data": data})
    if not _in_fallback():
        try:
            pipe = _redis.pipeline()
            key = f"progress:{analysis_id}"
            pipe.rpush(key, entry)
            pipe.expire(key, 3600)
            await pipe.execute()
            return
        except Exception:
            pass
    async with _fallback_progress_lock:
        buf = _fallback_progress.setdefault(analysis_id, [])
        is_terminal = status in ("complete", "error")
        if is_terminal or len(buf) < 200:
            buf.append({"message": message, "status": status, "data": data})


async def progress_get_all(analysis_id: str) -> list:
    if not _in_fallback():
        try:
            raw_list = await _redis.lrange(f"progress:{analysis_id}", 0, -1)
            return [json.loads(r) for r in raw_list]
        except Exception:
            pass
    return _fallback_progress.get(analysis_id, [])


async def progress_delete(analysis_id: str) -> None:
    if not _in_fallback():
        try:
            await _redis.delete(f"progress:{analysis_id}")
            return
        except Exception:
            pass
    _fallback_progress.pop(analysis_id, None)


# ─── Scan Counter (distributed semaphore) ───────────────────────────────────────

async def scan_acquire(max_concurrent: int = 5, timeout: float = 300) -> bool:
    """Try to acquire a scan slot. Returns True if slot acquired."""
    if not _in_fallback():
        try:
            key = "scan:active_slots"
            pipe = _redis.pipeline()
            pipe.incr(key)
            pipe.expire(key, timeout)
            result = await pipe.execute()
            count = result[0]
            if count <= max_concurrent:
                return True
            await _redis.decr(key)
            return False
        except Exception:
            pass
    return True


async def scan_release() -> None:
    if not _in_fallback():
        try:
            await _redis.decr("scan:active_slots")
            return
        except Exception:
            pass
