"""Bearer-token auth for the HTTP endpoint, as an ASGI middleware. Tokens map to users (tenant scope)."""
from __future__ import annotations

import hmac
import uuid

from .infra import current_trace, current_user


class BearerAuth:
    def __init__(self, app, tokens: dict[str, str]):
        self.app, self.tokens = app, tokens   # token -> user_id; load from env/DB, never hard-code

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = dict(scope["headers"])
        auth = headers.get(b"authorization", b"").decode()
        user = next((u for t, u in self.tokens.items()
                     if auth.startswith("Bearer ") and hmac.compare_digest(auth[7:], t)), None)
        if user is None:
            await send({"type": "http.response.start", "status": 401, "headers": [(b"content-type", b"text/plain")]})
            return await send({"type": "http.response.body", "body": b"unauthorized"})
        current_user.set(user)
        current_trace.set(headers.get(b"x-trace-id", uuid.uuid4().hex.encode()).decode())  # one trace id end-to-end
        return await self.app(scope, receive, send)
