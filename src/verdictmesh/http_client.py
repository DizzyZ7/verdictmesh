import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

import httpx

type Sleep = Callable[[float], Awaitable[None]]
type QueryParams = dict[str, str | int | float | bool]

_DEFAULT_RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    attempts: int = 3
    base_delay_seconds: float = 0.25
    max_delay_seconds: float = 2.0
    retry_statuses: frozenset[int] = field(default_factory=lambda: _DEFAULT_RETRY_STATUSES)

    def __post_init__(self) -> None:
        if self.attempts < 1:
            raise ValueError("attempts must be at least 1")
        if self.base_delay_seconds < 0:
            raise ValueError("base_delay_seconds cannot be negative")
        if self.max_delay_seconds < self.base_delay_seconds:
            raise ValueError("max_delay_seconds must be greater than or equal to base delay")

    def delay_seconds(self, failed_attempt: int, response: httpx.Response | None) -> float:
        retry_after = _retry_after_seconds(response)
        if retry_after is not None:
            return min(retry_after, self.max_delay_seconds)
        exponential = self.base_delay_seconds * (2 ** max(0, failed_attempt - 1))
        return min(exponential, self.max_delay_seconds)


async def get_with_retry(
    client: httpx.AsyncClient,
    url: str,
    *,
    params: QueryParams | None = None,
    policy: RetryPolicy | None = None,
    sleep: Sleep = asyncio.sleep,
) -> httpx.Response:
    """Execute an idempotent GET with bounded retries for transient failures."""
    resolved_policy = policy or RetryPolicy()

    for attempt in range(1, resolved_policy.attempts + 1):
        try:
            response = await client.get(url, params=params)
        except httpx.TransportError:
            if attempt >= resolved_policy.attempts:
                raise
            await sleep(resolved_policy.delay_seconds(attempt, None))
            continue

        retryable = response.status_code in resolved_policy.retry_statuses
        if not retryable or attempt >= resolved_policy.attempts:
            return response

        delay = resolved_policy.delay_seconds(attempt, response)
        await response.aclose()
        await sleep(delay)

    raise RuntimeError("retry loop exited unexpectedly")


def _retry_after_seconds(response: httpx.Response | None) -> float | None:
    if response is None:
        return None
    value = response.headers.get("Retry-After")
    if value is None:
        return None
    try:
        seconds = float(value)
    except ValueError:
        return None
    return max(0.0, seconds)
