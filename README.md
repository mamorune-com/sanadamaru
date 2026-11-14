# sanadamaru

**English** ・ [日本語](README.ja.md)

**A tiny, dependency-free honeypot for Python web apps. It puts decoy doors on the paths that automated scanners probe first, and tells you who touched them.**
It never hacks back. It never touches the other side's systems.

- Pure Python, no dependencies. Drops into FastAPI, Starlette and Flask in a few lines, and into anything that speaks ASGI or WSGI (Django included).
- Real users never open these paths, so a hit is a near-certain sign of probing. False positives are rare by design.
- Blocking is **off by default**. It only watches until you have checked how your proxy reports client addresses.

```text
GET /                                    → passed straight through to your app
GET /.env                                → 200, plausible but fake contents; logged (marker: env)
GET /api/admin/users
    Authorization: Bearer app_live_9e39…  → 403; logged (marker: env, field: db)
                                            "this key was taken from /.env, the DB_PASSWORD line"
```

Try it on your own machine (nothing is sent anywhere):

```bash
pip install "git+https://github.com/mamorune-com/sanadamaru@v0.2.1#subdirectory=python"
python -m sanadamaru demo    # the demo text is in Japanese for now
python -m sanadamaru doors   # list the default decoy paths
```

> **About the name.** Sanada-maru was an earthwork fort that the samurai commander Sanada Nobushige built outside the south wall of Osaka Castle in 1614. It stuck out from the main defenses, drew the attackers' attention, and protected the castle behind it. This library does the same job for your app: it is the outpost that scanners hit first.

## Why it works

Automated scanners, increasingly driven by AI agents, try far more paths than a human would, and never get tired. The first things they look for are the classic mistakes: a config file left public (`/.env`), a source history (`/.git/`), a database dump (`*.sql`). In August 2026, GreyNoise reported scanners posing as well-known AI crawlers, from more than 800 addresses, hunting for `/.env`, `/.env.production` and `/.aws/credentials` ([Help Net Security](https://www.helpnetsecurity.com/2026/08/31/ai-crawlers-scan-exposed-credentials/)).

Your real users never request `/.env`. So the moment someone does, you know with high confidence that they came looking. That is why sanadamaru avoids the flood of false alarms that most monitoring tools produce.

The bait keys tell you one step more. If someone takes a key from a decoy file and later tries to use it, they did not just look around: they tried to get in.

## What it does

| Defense | What happens |
|---|---|
| Decoy doors | 19 paths that scanners commonly probe (`/.env`, `/.git/config`, `/wp-login.php`, `*.sql`, `/actuator/env` and more) return plausible, entirely fake content. Every hit is recorded. |
| Marked bait keys | Each door contains fake keys, one per door and per field. If a bait key is presented later (in `Authorization`, `X-API-Key`, the query string and so on), the request is refused with 403 and you learn exactly which door and field it was taken from. |
| Records and alerts | Only the time, door, marker, source address and the start of the user agent are kept, in memory, with hard caps. Alerts are limited to one per door (marker) per hour. |
| Blocking (opt-in) | When enabled, a source that touched a door is refused for a while (24 hours by default). Health checks and emergency endpoints are never blocked. |

## Lines it never crosses

sanadamaru is a defensive component. These rules hold in every version and every configuration. Details: [docs/en/lines.md](docs/en/lines.md).

1. Never touch the other side's systems (no hack-back).
2. Never run anything on the visitor's machine. Decoy content is plain text only.
3. Never serve anything real. Every secret in a decoy is fake.
4. Never imitate another company's key format (no `AKIA…`, `sk_live_…`, `ghp_…`).
5. Never block uninvolved people.
6. Never block lifelines such as health checks and emergency endpoints.
7. Keep records to the minimum.
8. Respond through reports and takedown requests, not retaliation.

## Usage

### Install

```bash
pip install "git+https://github.com/mamorune-com/sanadamaru@v0.2.1#subdirectory=python"
```

Python 3.10 or later. The package is not on PyPI yet.

### FastAPI and Starlette

```python
from fastapi import FastAPI
from sanadamaru import Castle, SanadamaruMiddleware, log_alert

# Endpoints listed in never_block keep working even while blocking is on
castle = Castle.from_env(never_block=("/health", "/api/sos"), alert=log_alert)

app = FastAPI()
# … your other middleware and routes …
app.add_middleware(SanadamaruMiddleware, castle=castle)   # add it last so it is the outermost layer
```

### Flask

```python
from flask import Flask
from sanadamaru import Castle, SanadamaruWSGI, log_alert

castle = Castle.from_env(alert=log_alert)
app = Flask(__name__)
app.wsgi_app = SanadamaruWSGI(app.wsgi_app, castle=castle)
```

Django is covered in [docs/en/deploy.md](docs/en/deploy.md). Working examples live in [examples/](examples/), and CI runs them on every push.

### Configuration (environment variables)

| Name | Default | Meaning |
|---|---|---|
| `SANADAMARU_SECRET` | none | Seed for the bait keys (16 bytes or more). Always set it. Without it, the keys change on every restart. |
| `SANADAMARU_BAN` | `0` | Set to `1` to turn blocking on. |
| `SANADAMARU_BAN_SECONDS` | `86400` | How long a block lasts, in seconds. |
| `SANADAMARU_CLIENT_IP` | `direct` | How to read the client address: `direct`, `cloudflare` or `x-forwarded-for`. |
| `SANADAMARU_TRUSTED_HOPS` | `1` | With `x-forwarded-for`, the number of proxies in front of the app. |
| `SANADAMARU_TRUSTED_PROXIES` | | Address ranges of your proxies, comma-separated (for example `10.0.0.0/8`). Forwarding headers are only read when the request arrives from one of these. |
| `SANADAMARU_LOG_PER_MINUTE` | `60` | Maximum WARNING log lines per minute. Lines over the limit are counted and reported on the next line. |
| `SANADAMARU_NEVER_BLOCK` | | Paths that are never blocked, comma-separated. `/health` is always included. |
| `SANADAMARU_KEY_PREFIX` | `app_live_` | Prefix for the bait keys. Make it look like your own service's keys. Other companies' key formats are refused at startup. |

### Reading the records

`castle.report()` returns counts and the 50 most recent records. It contains full source addresses, so only expose it behind an admin key (see [examples/fastapi_app.py](examples/fastapi_app.py)).

### Getting alerts

Pass `alert=log_alert` and every alert is logged at ERROR level. Tools such as Sentry pick up ERROR logs, so the alert reaches you without extra setup. You can also pass your own function to send alerts to Slack or anywhere else. Alerts contain only the first part of the source address.

## Before you turn blocking on

The worst thing a blocker can do is lock out people who did nothing wrong. Before you enable it, follow [docs/en/deploy.md](docs/en/deploy.md) to confirm that client addresses are read correctly.

- Only Cloudflare in front: `SANADAMARU_CLIENT_IP=cloudflare`
- One proxy in front: `x-forwarded-for` with `SANADAMARU_TRUSTED_HOPS=1`
- A load balancer behind Cloudflare (Render, for example): `x-forwarded-for` with `SANADAMARU_TRUSTED_HOPS=2`
- Nothing in front: `direct`

As a safety net, Cloudflare's own addresses and non-public addresses (internal networks, load balancers and so on) are never blocked, whatever the setting. Forwarding headers (`CF-Connecting-IP`, `X-Forwarded-For`) are only read when they come from a trusted proxy. Requests made by a web page, such as `<img src=".../.env">` embedded on someone else's site, are recorded but never blocked, because the visitor did not choose to make them.

## Stage 2 (the tarpit): looking for collaborators

We are exploring a "stage 2" that would lead only the visitors who touched a door into an endless fake maze, so that their AI agents burn compute and time for nothing. Similar ideas exist, such as Cloudflare's [AI Labyrinth](https://blog.cloudflare.com/ai-labyrinth/).

A maze costs the defender something too, and it has to stay inside the lines above. So before building anything, we are looking for people to help with the design. Conditions and open questions: [docs/en/stage2.md](docs/en/stage2.md).

## Limitations

- It cannot see attacks that go straight for your real endpoints without probing a door. It does not replace authentication, authorization or input validation.
- The decoy paths are well known. An attacker who knows about sanadamaru can avoid them. The bait keys, however, are unique to each installation.
- Records and blocks live in memory only. They are lost on restart and are not shared between processes or servers.

## Documentation

- [docs/en/how-it-works.md](docs/en/how-it-works.md): how it works (order of checks, how bait keys are made, how client addresses are read, porting to other languages)
- [docs/en/deploy.md](docs/en/deploy.md): checks to run when you install it
- [docs/en/lines.md](docs/en/lines.md): the lines it never crosses
- [docs/en/stage2.md](docs/en/stage2.md): the stage 2 call for collaborators
- [SECURITY.md](SECURITY.md): reporting a vulnerability
- [CONTRIBUTING.md](CONTRIBUTING.md): adding doors, porting to other languages
- [CHANGELOG.md](CHANGELOG.md): release notes (Japanese)

## Related projects

- [Canarytokens](https://canarytokens.org/) by Thinkst: free tripwires you plant in documents, URLs and credentials.
- [AI Labyrinth](https://blog.cloudflare.com/ai-labyrinth/) by Cloudflare: a maze of generated pages for crawlers that ignore robots.txt.

## License

Apache-2.0. Free to use, including commercially.

Built by MAMORUNE Inc. to protect its own services, and released for anyone to use. Its sister project is [kango](https://github.com/mamorune-com/kango), a phishing check that matches incoming messages against your own list of contracted companies and their official domains.
