# Upstream resilience

VerdictMesh applies bounded retries only to idempotent GET requests sent to Gamma, CLOB and GDELT.

## Default policy

- maximum attempts: 3;
- exponential delays: 250 ms, then 500 ms;
- maximum delay: 2 seconds;
- retryable responses: `429`, `500`, `502`, `503`, `504`;
- retryable exceptions: `httpx.TransportError`;
- numeric `Retry-After` is respected but capped by the maximum delay.

Responses such as `400`, `401`, `403` and `404` are returned immediately because repeating an invalid request does not improve reliability and can amplify provider load.

## Anthropic requests

Forecast requests use `POST /v1/messages` and are intentionally not retried automatically. A transport failure can occur after the provider accepted the request, so an automatic retry could create duplicate forecasts or duplicate model charges. Safe retries for model calls require provider-supported idempotency semantics and persisted request identifiers.

## Custom policies in tests or adapters

Each GET client accepts an optional `RetryPolicy`, so tests and future deployments can use a smaller attempt count or different delays without changing the shared implementation.

```python
from verdictmesh.http_client import RetryPolicy

policy = RetryPolicy(
    attempts=2,
    base_delay_seconds=0.1,
    max_delay_seconds=0.5,
)
```

Timeouts remain explicit per provider client. Retries are bounded and do not turn a failed upstream into an unbounded request.
