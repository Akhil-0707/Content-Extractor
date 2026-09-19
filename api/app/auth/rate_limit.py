import time

from fastapi import HTTPException, status
from redis.asyncio import Redis

from app.config import settings

redis = Redis.from_url(settings.redis_url)


async def enforce_rate_limit(bucket: str, identity: str | None, limit: int, message: str) -> None:
    """Fixed one-minute window per (bucket, identity)."""
    key = f"rl:{bucket}:{identity or 'unknown'}:{int(time.time() // 60)}"
    count = await redis.incr(key)
    if count == 1:
        await redis.expire(key, 60)
    if count > limit:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, message)


async def check_login_rate(ip: str | None) -> None:
    await enforce_rate_limit(
        "login", ip, settings.login_rate_limit_per_minute, "Too many login attempts. Try again in a minute."
    )
