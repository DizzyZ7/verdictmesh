from collections.abc import Callable

import httpx
import pytest

from verdictmesh.http_client import RetryPolicy, get_with_retry


@pytest.mark.asyncio
async def test_retries_transient_statuses_and_respects_retry_after() -> None:
    attempts = 0
    delays: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(503, request=request)
        if attempts == 2:
            return httpx.Response(429, headers={"Retry-After": "0.05"}, request=request)
        return httpx.Response(200, json={"ok": True}, request=request)

    async def fake_sleep(delay: float) -> None:
        delays.append(delay)

    async with httpx.AsyncClient(
        base_url="https://provider.test",
        transport=httpx.MockTransport(handler),
    ) as client:
        response = await get_with_retry(
            client,
            "/resource",
            policy=RetryPolicy(
                attempts=3,
                base_delay_seconds=0.1,
                max_delay_seconds=0.5,
            ),
            sleep=fake_sleep,
        )

    assert response.status_code == 200
    assert attempts == 3
    assert delays == pytest.approx([0.1, 0.05])


@pytest.mark.asyncio
async def test_retries_transport_errors() -> None:
    attempts = 0
    delays: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise httpx.ConnectError("temporary failure", request=request)
        return httpx.Response(200, request=request)

    async def fake_sleep(delay: float) -> None:
        delays.append(delay)

    async with httpx.AsyncClient(
        base_url="https://provider.test",
        transport=httpx.MockTransport(handler),
    ) as client:
        response = await get_with_retry(
            client,
            "/resource",
            policy=RetryPolicy(attempts=2, base_delay_seconds=0.2),
            sleep=fake_sleep,
        )

    assert response.status_code == 200
    assert attempts == 2
    assert delays == pytest.approx([0.2])


@pytest.mark.asyncio
async def test_does_not_retry_non_transient_client_errors() -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(400, request=request)

    async def fail_if_called(_: float) -> None:
        raise AssertionError("sleep should not be called")

    async with httpx.AsyncClient(
        base_url="https://provider.test",
        transport=httpx.MockTransport(handler),
    ) as client:
        response = await get_with_retry(
            client,
            "/resource",
            policy=RetryPolicy(attempts=3),
            sleep=fail_if_called,
        )

    assert response.status_code == 400
    assert attempts == 1


@pytest.mark.parametrize(
    ("factory", "message"),
    [
        (lambda: RetryPolicy(attempts=0), "at least 1"),
        (lambda: RetryPolicy(base_delay_seconds=-1), "cannot be negative"),
        (
            lambda: RetryPolicy(base_delay_seconds=2, max_delay_seconds=1),
            "greater than or equal",
        ),
    ],
)
def test_retry_policy_validation(
    factory: Callable[[], RetryPolicy],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        factory()
