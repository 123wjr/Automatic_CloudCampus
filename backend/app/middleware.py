import time
from collections import defaultdict
from fastapi import Request, HTTPException


class RateLimiter:
    def __init__(self, max_requests: int = 5, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window = window_seconds
        self._clients: dict[str, list[float]] = defaultdict(list)

    async def __call__(self, request: Request):
        client = request.client.host if request.client else "unknown"
        now = time.time()
        self._clients[client] = [t for t in self._clients[client] if now - t < self.window]
        self._clients[client].append(now)
        if len(self._clients[client]) > self.max_requests:
            raise HTTPException(status_code=429, detail="请求过于频繁，请稍后再试")

    def cleanup(self):
        now = time.time()
        stale = [k for k, v in self._clients.items() if not v or now - v[-1] > self.window * 2]
        for k in stale:
            del self._clients[k]


_login_limiter = RateLimiter(max_requests=5, window_seconds=60)
_admin_limiter = RateLimiter(max_requests=5, window_seconds=60)


def get_login_limiter() -> RateLimiter:
    return _login_limiter


def get_admin_limiter() -> RateLimiter:
    return _admin_limiter
