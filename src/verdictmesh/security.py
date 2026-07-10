import hmac
from collections.abc import Awaitable, Callable
from uuid import uuid4

from fastapi import FastAPI, Request
from starlette.responses import JSONResponse, Response

from verdictmesh.config import Settings

type CallNext = Callable[[Request], Awaitable[Response]]

_PUBLIC_PATHS = frozenset({"/health", "/openapi.json"})
_PUBLIC_PREFIXES = ("/docs", "/redoc")


def install_security_middleware(app: FastAPI, settings: Settings) -> None:
    """Install operator authentication and conservative response headers."""

    @app.middleware("http")
    async def security_middleware(request: Request, call_next: CallNext) -> Response:
        request_id = request.headers.get("X-Request-ID") or uuid4().hex
        request.state.request_id = request_id

        if _requires_authentication(request) and not _is_authorized(request, settings):
            response: Response = JSONResponse(
                status_code=401,
                content={"detail": "Invalid or missing operator API key"},
                headers={"WWW-Authenticate": "ApiKey"},
            )
        else:
            response = await call_next(request)

        response.headers.setdefault("X-Request-ID", request_id)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault(
            "Permissions-Policy",
            "camera=(), microphone=(), geolocation=()",
        )
        return response


def _requires_authentication(request: Request) -> bool:
    if request.method == "OPTIONS":
        return False
    path = request.url.path
    if path in _PUBLIC_PATHS:
        return False
    return not path.startswith(_PUBLIC_PREFIXES)


def _is_authorized(request: Request, settings: Settings) -> bool:
    secret = settings.operator_api_key
    if secret is None:
        return True

    provided = request.headers.get(settings.operator_api_key_header)
    if provided is None:
        return False

    return hmac.compare_digest(provided, secret.get_secret_value())
