# Checks to run when you install it

**English** ・ [日本語](../deploy.md)

## 1. Make sure no decoy path collides with a real endpoint

Run `python -m sanadamaru doors` to list the default decoy paths, and check that your app has no real endpoint at any of them. If it does, remove that door. Otherwise real users will be recorded, and blocked if blocking is on.

```python
from sanadamaru import Castle, default_doors

doors = default_doors()
doors.pop("/actuator/env")          # remove any path your app really uses
castle = Castle.from_env(doors=doors)
```

The rules for adding doors are in [CONTRIBUTING.md](../../CONTRIBUTING.md).

## 2. Choose a secret

Put a random value of 16 bytes or more in `SANADAMARU_SECRET`.

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

- Treat it like a real key: keep it in an environment variable, never in code.
- If you change the secret, bait keys that were taken earlier can no longer be matched.

## 3. Make it the outermost layer

Put it outside your other middleware (authentication, CORS and so on).

```python
# FastAPI / Starlette: the last middleware added is the outermost
app.add_middleware(SanadamaruMiddleware, castle=castle)

# Flask
app.wsgi_app = SanadamaruWSGI(app.wsgi_app, castle=castle)

# Django (asgi.py)
application = SanadamaruMiddleware(get_asgi_application(), castle=castle)

# Django (wsgi.py)
application = SanadamaruWSGI(get_wsgi_application(), castle=castle)
```

## 4. List the endpoints that must never stop

Put your health check (`/health`) and any emergency endpoints in `never_block`. They stay open while blocking is on, and a bait key presented to them is recorded but not refused.

```python
castle = Castle.from_env(never_block=("/health", "/api/sos"))
# or with an environment variable: SANADAMARU_NEVER_BLOCK=/api/sos (/health is always included)
```

## 5. Protect the records endpoint with an admin key

`castle.report()` contains full source addresses. Do not serve it at a public path; expose it only behind an admin key. Compare keys with `hmac.compare_digest` so that timing differences do not leak the key (see [examples/fastapi_app.py](../../examples/fastapi_app.py)).

## 6. Send alerts to the people who run the service

```python
from sanadamaru import Castle, log_alert
castle = Castle.from_env(alert=log_alert)   # logged at ERROR level, where Sentry and similar tools pick it up
```

You can also write your own function to send alerts to Slack or elsewhere. It receives one record that contains only the first part of the source address.

## 7. Turn blocking on only after a few days of watching

1. Install it in watch-only mode first (the default).
2. Open a door yourself once (for example, `https://your-service/.env` in a browser).
3. In the records (`recent` in `report()`), check that `ip` is the address of your own connection.
   - If it is a Cloudflare address (starting with `104.16.`, `172.64.` and so on), the client address is being read the wrong way.
   - If it is empty, the address is not being read at all.
4. If it is correct, watch for a few days and look at how many records come in and what they contain.
5. Turn blocking on (`SANADAMARU_BAN=1`).

| What is in front of the app | `SANADAMARU_CLIENT_IP` | `SANADAMARU_TRUSTED_HOPS` |
|---|---|---|
| Nothing | `direct` | |
| Only Cloudflare (the direct peer is a Cloudflare address) | `cloudflare` | |
| One proxy that appends the client address to the right end of `X-Forwarded-For` | `x-forwarded-for` | `1` |
| Two such proxies (for example, a load balancer behind Cloudflare, as on Render) | `x-forwarded-for` | `2` |

- Forwarding headers are only read when the direct peer is a trusted proxy. With `x-forwarded-for`, non-public addresses (such as a load balancer in the same data center) are treated as trusted proxies. If your load balancer or CDN uses public addresses, list its ranges in `SANADAMARU_TRUSTED_PROXIES`.
- If you have a load balancer behind Cloudflare and choose `cloudflare`, the direct peer is the load balancer, so the header is not read (`ip` becomes the load balancer's address and nothing is blocked). Choose `x-forwarded-for` with `2` instead.
- If the number of hops is wrong, `ip` is empty (nothing is blocked). You will notice this in step 3.

**Once blocking is on, do not test the doors yourself.** Your own connection will be blocked too (for 24 hours by default). To lift a block, restart the app (blocks live in memory).

## 8. Use the records through legitimate channels

Use the records to contact your local police or cybercrime reporting service, your national CERT, or the abuse contact of the provider that owns the attacking address. Never retaliate ([the lines it never crosses](lines.md)).
