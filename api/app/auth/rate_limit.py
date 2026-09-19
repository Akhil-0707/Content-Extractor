import time

from fastapi import HTTPException, status
from redis.asyncio import Redis

from app.config import settings

redis = Redis.from_url(settings.redis_url)


async def check_login_rate(ip: str | None) -> None:
    """Fixed one-minute window per client IP."""
    key = f"rl:login:{ip or 'unknown'}:{int(time.time() // 60)}"
    count = await redis.incr(key)
    if count == 1:
        await redis.expire(key, 60)
    if count > settings.login_rate_limit_per_minute:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many login attempts. Try again in a minute.")
