"""Redis cache helpers.

Thin wrapper around redis-py with graceful degradation:
if Redis is unavailable, all operations silently return None /
do nothing so the bot keeps working without cache.
"""

import json
import logging

import redis

import config

logger = logging.getLogger(__name__)

_client: redis.Redis | None = None
_client_broken = False


def _get_client() -> redis.Redis | None:
    """Lazily create (or re-create after failure) the Redis client."""
    global _client, _client_broken
    if _client is not None and not _client_broken:
        return _client
    try:
        _client = redis.Redis.from_url(
            config.REDIS_URL,
            decode_responses=True,
            socket_timeout=2,
            socket_connect_timeout=2,
        )
        _client.ping()
        _client_broken = False
        logger.info("Redis cache connected: %s", config.REDIS_URL)
    except Exception as e:  # noqa: BLE001
        _client_broken = True
        logger.warning("Redis unavailable, cache disabled: %s", e)
        return None
    return _client


def get_json(key: str):
    """Get a JSON-serializable value from cache. Returns None on miss/error."""
    client = _get_client()
    if client is None:
        return None
    try:
        raw = client.get(key)
        if raw is None:
            return None
        return json.loads(raw)
    except Exception as e:  # noqa: BLE001
        logger.warning("Redis GET failed for %s: %s", key, e)
        return None


def set_json(key: str, value, ttl: int | None = None) -> bool:
    """Set a JSON-serializable value with an optional TTL (seconds)."""
    client = _get_client()
    if client is None:
        return False
    try:
        client.set(key, json.dumps(value), ex=ttl)
        return True
    except Exception as e:  # noqa: BLE001
        logger.warning("Redis SET failed for %s: %s", key, e)
        return False


def delete(key: str) -> None:
    """Delete a cache key (best effort)."""
    client = _get_client()
    if client is None:
        return
    try:
        client.delete(key)
    except Exception as e:  # noqa: BLE001
        logger.warning("Redis DELETE failed for %s: %s", key, e)


def subscription_whitelist_key(panel_subscription_id) -> str:
    """Cache key for the whitelist-bypass traffic of a subscription."""
    return f"sub:wl:{panel_subscription_id}"