# Lines sanadamaru never crosses

**English** ・ [日本語](../lines.md)

sanadamaru is a defensive component. The urge to "get back at" an attacker is exactly when people cross lines they should not.

The lines below hold in every version and every configuration. Check every new feature and every new door against them.

> Any mention of law here is general information, not legal advice. The original project is Japanese, so Japanese law is cited, but most countries have similar rules. Talk to a lawyer about your own jurisdiction if you install or modify sanadamaru.

## 1. Never touch the other side's systems (no hack-back)

sanadamaru sends nothing to the other side. It does not query their address, probe their machine or try to take it down.

- Accessing someone else's computer without permission is a crime in most countries (in Japan, the Act on Prohibition of Unauthorized Computer Access; in the US, the Computer Fraud and Abuse Act; in the UK, the Computer Misuse Act 1990). That holds even when the other side is an attacker.
- Attacks often come from hijacked machines that belong to uninvolved people. Retaliation hurts them.

## 2. Never run anything on the visitor's machine

Decoy content is plain text only. sanadamaru never returns scripts, files designed to overload the client (such as zip bombs), or anything else that executes on the other side.

- Creating or planting software that makes a computer act against its user's intent can be a crime (in Japan, the offence concerning unauthorized command electromagnetic records, often called the "virus crime").
- A test checks on every run that the default decoys contain no `<script`.

## 3. Never serve anything real

Everything inside a decoy is fake. No real keys, settings or user data. No names or email addresses that look like real people.

- If anything real slipped into a decoy, the defensive component itself would become the leak.
- Decoy hostnames use names that cannot resolve from outside (`.internal`) and private addresses (`10.x.x.x`) only.

## 4. Never imitate another company's key format

Bait keys should look like your own service's keys. They never imitate real formats used by other companies, such as AWS (`AKIA…`), Stripe (`sk_live_…`) or GitHub (`ghp_…`).

- A look-alike key can make that company, or a secret scanner, react as if a real key had leaked, which wastes uninvolved people's time.
- If `key_prefix` imitates another company's format, sanadamaru refuses to start (the list is `FOREIGN_KEY_PREFIXES` in `castle.py`).

## 5. Never block uninvolved people

Blocking is off by default. Turn it on only after confirming that client addresses are read correctly ([deploy.md](deploy.md)).

- Blocking the address of a proxy in front of you (Cloudflare or a load balancer) blocks everyone behind it. So Cloudflare's own addresses and non-public addresses are never blocked, whatever the setting.
- The left side of `X-Forwarded-For` can be written freely by the caller. Blocking on it would let anyone write someone else's address and get an innocent person blocked. sanadamaru only uses the right-hand entries added by your own proxies.
- The forwarding headers themselves (`CF-Connecting-IP`, `X-Forwarded-For`) can be forged too if the request bypasses the proxy. sanadamaru reads them only when the direct peer is confirmed to be a trusted proxy. If the number of hops does not match, it does not block.
- Anyone can put `<img src="https://your-service/.env">` on their own page, and every browser that views that page will open the door. When the browser marks a request as loaded by a page (`Sec-Fetch-Site`, `Referer`, `Origin`), sanadamaru records it but does not block. On http:// addresses or with `referrerpolicy="no-referrer"`, all of these marks can disappear. So when there are no marks but the user agent identifies itself as a browser (`Mozilla/…`), sanadamaru does not block either (except when `Sec-Fetch-Site: none` shows the address was typed in directly). This leaves a loophole that makes blocking easier to dodge, but we choose not to catch uninvolved people. Every case is still recorded.
- On mobile networks and similar, many people can share one address. Blocks always expire (24 hours by default).

## 6. Never block lifelines

Health checks and emergency endpoints (for example, an endpoint that sends a "help me" message to someone's family) stay open even while blocking is on (`never_block`). If a bait key is presented to one of them, the request is recorded but not refused.

- A defensive component must never silence a call for help.

## 7. Keep records to the minimum

Only the time, door, marker, source address and the start of the user agent (up to 120 characters) are recorded. Request bodies and cookies are never kept.

- Records live in memory only, with a cap on their number, so an attacker cannot exhaust your memory.
- Alerts and log lines show only the first part of the source address. The full list with complete addresses (`report()`) should only be exposed behind an admin key.
- Control characters such as line breaks are replaced with "?" before recording, so log lines cannot be forged.

## 8. Respond through reports and takedown requests

Use the records through legitimate channels, for example:

- your local police or cybercrime reporting service
- your national CERT (JPCERT/CC in Japan, CISA in the US, the NCSC in the UK, and so on)
- the abuse contact of the provider or cloud company that owns the attacking address

## Changing these lines

Changes that loosen these lines will not be merged. Proposals to rethink a line itself are discussed in an issue, with reasons.
