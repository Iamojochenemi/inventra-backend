"""
Request tracing middleware.

Provides a unique request_id for every request, propagated to:
- The JSON logging formatter (via a ContextVar)
- The response headers (as X-Request-ID)
- The request object (request.request_id)
"""

import uuid
from contextvars import ContextVar

# ContextVar — safe for both sync and async Django runtimes.
# The logging formatter reads this on every log record emission
# within the same request lifecycle.
request_id_var: ContextVar[str] = ContextVar("request_id", default="")


class RequestTracingMiddleware:
    """
    Extracts or generates an X-Request-ID for every incoming request.

    Priority:
        1. X-Request-ID header supplied by a reverse proxy / client
        2. Fresh UUID4

    The ID is stored in three places:
        - request.request_id          (for views / services)
        - request_id_var ContextVar   (for the JSON log formatter)
        - response["X-Request-ID"]    (for downstream tracing)
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # ── 1. Extract or generate ────────────────────────
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())

        # ── 2. Stamp the request object ───────────────────
        request.request_id = request_id

        # ── 3. Set the context var (read by JSONFormatter) ─
        token = request_id_var.set(request_id)

        try:
            response = self.get_response(request)
        finally:
            # ── 4. Stamp the response for downstream tracing ─
            response["X-Request-ID"] = request_id
            # ── 5. Clean up the context var ────────────────
            request_id_var.reset(token)

        return response
