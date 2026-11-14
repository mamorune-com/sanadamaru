# How it works

**English** ・ [日本語](../how-it-works.md)

The core of sanadamaru is `Castle.check` ([python/sanadamaru/castle.py](../../python/sanadamaru/castle.py)). The adapters for FastAPI, Flask and so on (`asgi.py`, `wsgi.py`) simply hand each request to `Castle.check`.

## Order of checks

`Castle.check` looks at each request in this order:

1. **Is the source blocked?** (only when blocking is on). If so, it returns 403. Paths in `never_block` skip this step.
2. **Is this a decoy door?** If so, it returns the fake content with 200 and records the hit.
3. **Was a bait key presented?** If so, it records the hit and returns 403. On `never_block` paths it records the hit and lets the request through.
4. Otherwise it does nothing and passes the request to your real endpoints (it returns `None`).

## Decoy doors

- Paths are normalized before comparison: `//` becomes `/` and a trailing `/` is removed. Matching is case-sensitive.
- The content is generated once at startup and the same content is returned every time, because a real config file does not change between reads.
- The response headers are `Content-Type`, `X-Content-Type-Options: nosniff` and `Cache-Control: no-store`. If a cache in between kept the content, later probes would never reach the records, so caching is disabled.
- HEAD requests get the length only, with no body.
- A door is a door whatever the method (GET, POST and so on).

## Marked bait keys

```text
bait key = prefix (key_prefix) + first 32 hex characters of HMAC-SHA256(secret, "sanadamaru/v1" ‖ marker ‖ field)
```

- The same secret, marker and field always produce the same key. A different secret produces different keys, so every installation has its own.
- The marker and field are not visible in the key. Looking at a key does not tell the other side which door it came from.
- Matching compares against the exact list of generated keys. A key with the right prefix that is not on the list is not treated as a bait key.
- Places checked: `Authorization` (Bearer, and the password part of Basic), `X-API-Key`, `X-Admin-Key`, `X-Auth-Token`, `X-Access-Token`, and everything after `?`. Request bodies are not read. The length searched in each value is capped.
- You can also make keys to plant outside the doors with `castle.bait_key("marker", "field")`. Put one in a fake document, for example, and you will know if it is ever used.

## Reading the client address

| `client_ip` | Where it reads | When to use it |
|---|---|---|
| `direct` | The peer that connected directly | Nothing in front of the app |
| `cloudflare` | `CF-Connecting-IP` (Cloudflare overwrites it) | Only Cloudflare in front |
| `x-forwarded-for` | The `trusted_hops`-th entry from the right of `X-Forwarded-For` | A load balancer or similar in front (including a load balancer behind Cloudflare) |

- Headers are read only when the direct peer is confirmed to be a trusted proxy: a Cloudflare address for `cloudflare`, and an address in `trusted_proxies` for `x-forwarded-for` (or any non-public address if `trusted_proxies` is not set). IPv4 ranges written in IPv6 form, such as `::ffff:1.2.3.0/120`, are also compared as IPv4 ranges (`1.2.3.0/24`). Headers from any other peer are ignored and the peer's own address is used.
- When `trusted_hops` is 2 or more, the addresses in between must also be trusted proxies (`trusted_proxies`, Cloudflare, or non-public addresses if `trusted_proxies` is not set).
- If a request comes from a trusted proxy but the header is missing or too short, the address is left empty (no blocking; a WARNING is logged the first time only).
- Values with decorations such as `%scope`, or with characters that never appear in an address, are not read as addresses.
- The left side of `X-Forwarded-For` can be written freely by the caller, so it is never used.

## Blocking

- Blocks expire (24 hours by default) and lift automatically.
- The number of blocked addresses is capped (10,000 by default), so an attacker rotating addresses cannot exhaust your memory.
- Never blocked: Cloudflare's own addresses, non-public addresses (internal, home, CGNAT, loopback, documentation ranges and so on) and unreadable addresses.
- Requests made by a page are not blocked: when `Sec-Fetch-Site` is anything other than `none` (cross-site, same-site, same-origin), when `Referer` or `Origin` is present, or when there are no marks at all and the user agent identifies itself as a browser (`Mozilla/…`), because http:// addresses and `referrerpolicy="no-referrer"` can strip the marks. With `Sec-Fetch-Site: none` (the address was typed in) the source is blocked. Such requests are recorded with `from_page`.

## Records and alerts

`castle.report()` returns:

| Name | Contents |
|---|---|
| `total` | Hits on doors and bait keys since startup |
| `by_door` | Hits per door |
| `bait_key_by_marker` | Bait key uses per marker |
| `sources` | Number of distinct sources in recent records |
| `banned_now`, `blocked` | Sources blocked right now, and requests refused by blocking |
| `log_lines_not_written` | Log lines skipped because of the per-minute limit |
| `recent` | The 50 most recent records, newest first |

- Each record holds the time, kind, method, path, marker, field, source address and its first part, the start of the user agent, whether the request came from a page, and whether it was blocked.
- Paths and user agents are stored with control characters, invisible formatting characters (such as U+202E, which reverses text direction) and line separators replaced with "?", and are truncated to a fixed length. If your service puts real keys in paths, note that those keys will appear in the records too (nothing after `?` is kept).
- Log lines (`logging` at WARNING) show only the first part of the source address. Up to `log_per_minute` lines are written per minute (60 by default); lines over the limit are counted and the next line ends with "(+N not logged)".
- Alerts (`alert`) are sent at most once per kind and marker every `alert_cooldown` seconds (one hour by default). The record passed to the alert contains only the first part of the source address. If an alert fails, the defense keeps working.

## Multiple processes and servers

Records and blocks live in each process's memory. With several processes or servers, each records and blocks on its own. Bait keys are derived from the secret, so every process produces the same keys and a key is recognized wherever it is used.

## Porting to other languages

If you port sanadamaru to Express, Go, Rails or anything else, keep these the same:

- The order of checks (1 to 4 above)
- How bait keys are made (the same secret, marker and field give the same key)
- How client addresses are read, and which addresses are never blocked
- Replacement of control and invisible formatting characters, and the caps on records (count and lines per minute)
- Never blocking requests made by a page
- [The lines it never crosses](lines.md)

Use the tests in [python/tests/](../../python/tests/) as the model for your port's tests.
