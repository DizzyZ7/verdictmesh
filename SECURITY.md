# Security policy

## Supported code

Security fixes are applied to the current `main` branch. VerdictMesh is experimental,
paper-trading software and does not currently support live execution.

## Reporting a vulnerability

Do not publish credentials, exploit payloads, private market data, or a working proof of
concept in a public issue. Prefer GitHub private vulnerability reporting for this repository.
When private reporting is unavailable, open a minimal issue that asks the maintainer for a
private contact channel without including sensitive technical details.

Include the affected commit, deployment mode, reproduction steps, impact, and a proposed
mitigation when possible.

## Operator authentication

VerdictMesh protects every route except `/health`, `/docs`, `/redoc`, and `/openapi.json`
when `OPERATOR_API_KEY` is configured.

- Use a random secret of at least 32 characters.
- Send it in the header configured by `OPERATOR_API_KEY_HEADER` (`X-API-Key` by default).
- `APP_ENV=staging` and `APP_ENV=production` fail at startup when the key is missing.
- Development remains open when the key is unset to preserve the local quick-start flow.

Generate a key locally:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Example request:

```bash
curl -H "X-API-Key: $OPERATOR_API_KEY" http://localhost:8000/markets
```

## Deployment checklist

- Keep `LIVE_TRADING_ENABLED=false`.
- Store API and model-provider keys in a secret manager, never in Git.
- Terminate TLS at a trusted reverse proxy and restrict direct access to the API container.
- Use a dedicated PostgreSQL user and a non-default password.
- Back up the database and test Alembic upgrades and downgrades before deployment.
- Restrict outbound network access to required providers.
- Monitor model-provider spend, forecast calls, scanner failures, and authentication failures.
- Rotate credentials after any suspected disclosure.

The container runs as an unprivileged user and exposes a health check, but production
hardening still depends on the surrounding host, network, proxy, and secrets configuration.
