"""How client addresses (IP addresses) are read, and which addresses may be blocked.

The most important thing about blocking is never catching uninvolved people (rule 5 in docs/en/lines.md).
So an address we are not sure about is never blocked.

- Cloudflare's own addresses carry traffic for many users. Blocking one would block all of them.
- Non-public addresses (internal, home, CGNAT, loopback and so on) usually belong to something in front of the app,
  such as a load balancer. Blocking one would also block everyone.
"""
from __future__ import annotations

import ipaddress
import re
from typing import Iterable, Mapping, Optional, Sequence, Tuple, Union

_Address = Union[ipaddress.IPv4Address, ipaddress.IPv6Address]
_Network = Union[ipaddress.IPv4Network, ipaddress.IPv6Network]
_IP_CHARS = re.compile(r"[0-9A-Fa-f:.]+")   # only characters used in addresses (decorations such as `%scope` are refused)

# Address ranges published by Cloudflare (https://www.cloudflare.com/ips/, as of 2026-10).
# They can change, so review them from time to time.
CLOUDFLARE_NETWORKS = tuple(ipaddress.ip_network(n) for n in (
    "173.245.48.0/20", "103.21.244.0/22", "103.22.200.0/22", "103.31.4.0/22", "141.101.64.0/18",
    "108.162.192.0/18", "190.93.240.0/20", "188.114.96.0/20", "197.234.240.0/22", "198.41.128.0/17",
    "162.158.0.0/15", "104.16.0.0/13", "104.24.0.0/14", "172.64.0.0/13", "131.0.72.0/22",
    "2400:cb00::/32", "2606:4700::/32", "2803:f800::/32", "2405:b500::/32", "2405:8100::/32",
    "2a06:98c0::/29", "2c0f:f248::/32",
))


def parse(value: Optional[str]) -> Optional[_Address]:
    """Return the address if it can be read as one. Also reads values with a port, such as `1.2.3.4:5678` or `[2001:db8::1]:443`."""
    s = (value or "").strip()
    if not s:
        return None
    if s.startswith("["):                      # [IPv6]:port
        s = s[1:].split("]", 1)[0]
    elif s.count(":") == 1:                    # IPv4:port
        s = s.split(":", 1)[0]
    if not _IP_CHARS.fullmatch(s):             # values with decorations such as `fe80::1%eth0`, or with control characters, are not read
        return None
    try:
        a = ipaddress.ip_address(s)
    except ValueError:
        return None
    if isinstance(a, ipaddress.IPv6Address) and a.ipv4_mapped is not None:
        return a.ipv4_mapped                   # treat ::ffff:1.2.3.4 as 1.2.3.4
    return a


def networks(values: Iterable[str]) -> Tuple[_Network, ...]:
    """Read a list of ranges such as `10.0.0.0/8`. Raises ValueError if any range cannot be read (refuse to run with a wrong setting).

    An IPv4 range written in IPv6 form, such as `::ffff:1.2.3.0/120`, is also kept as the IPv4 range (`1.2.3.0/24`).
    parse() turns `::ffff:1.2.3.4` into `1.2.3.4`, so ranges must take the same form to match.
    """
    out = []
    for v in values:
        try:
            n = ipaddress.ip_network(str(v).strip(), strict=False)
        except ValueError:
            raise ValueError(f"not a valid address range: {v!r}") from None
        out.append(n)
        if isinstance(n, ipaddress.IPv6Network) and n.prefixlen >= 96:
            mapped = n.network_address.ipv4_mapped
            if mapped is not None:
                out.append(ipaddress.ip_network(f"{mapped}/{n.prefixlen - 96}", strict=False))
    return tuple(out)


def _within(a: Optional[_Address], nets: Sequence[_Network]) -> bool:
    return a is not None and any(a.version == n.version and a in n for n in nets)


def is_cloudflare(ip: Optional[str]) -> bool:
    return _within(parse(ip), CLOUDFLARE_NETWORKS)


def banable(ip: Optional[str]) -> bool:
    """Whether an address may be blocked. Only public (global) addresses that are not Cloudflare's own."""
    a = parse(ip)
    if a is None or not a.is_global or a.is_multicast:
        return False
    return not is_cloudflare(str(a))


def client_ip(
    mode: str,
    headers: Mapping[str, str],
    peer: Optional[str],
    trusted_hops: int = 1,
    trusted_proxies: Sequence[_Network] = (),
) -> str:
    """The client address used for blocking and records. An empty string when it cannot be confirmed (empty addresses are never blocked).

    Callers can write headers (`CF-Connecting-IP`, `X-Forwarded-For`) freely. So the headers are read only when the
    direct peer is confirmed to be something in front of the app (a trusted proxy). If an unconfirmed peer sends
    these headers, they are ignored and the peer's own address is used.

    - direct: the peer that connected directly (nothing in front of the app)
    - cloudflare: `CF-Connecting-IP`, read only when the direct peer is a Cloudflare address (or inside trusted_proxies).
    - x-forwarded-for: the trusted_hops-th entry from the right of `X-Forwarded-For`, read only when the direct peer is
      inside trusted_proxies (or, if none are given, a non-public address such as a load balancer in the same data center).
      When trusted_hops is 2 or more, the addresses in between must also be trusted proxies (trusted_proxies, Cloudflare,
      or non-public addresses if none are given). If the number of hops does not match, the result is empty.
      The left side can be written freely by the caller, so it is never used.
    """
    p = parse(peer)
    own = str(p) if p is not None else ""
    if mode == "cloudflare":
        if not (_within(p, CLOUDFLARE_NETWORKS) or _within(p, trusted_proxies)):
            return own                         # arrived without passing Cloudflare; the header could be forged, so do not read it
        a = parse(headers.get("cf-connecting-ip"))
        return str(a) if a is not None else ""
    if mode == "x-forwarded-for":
        def is_proxy(a: Optional[_Address]) -> bool:
            if trusted_proxies:
                return _within(a, trusted_proxies)
            return a is not None and not a.is_global
        if not is_proxy(p):
            return own                         # arrived without passing a trusted proxy; the header could be forged, so do not read it
        parts = [x.strip() for x in (headers.get("x-forwarded-for") or "").split(",") if x.strip()]
        hops = int(trusted_hops)
        if len(parts) < hops:
            return ""                          # wrong number of hops; never read the left side (which the caller can write)
        chain = [parse(x) for x in parts[len(parts) - hops:]]
        if any(a is None for a in chain):
            return ""
        for middle in chain[1:]:
            if not (is_proxy(middle) or _within(middle, CLOUDFLARE_NETWORKS)):
                return ""                      # an address in between is not a trusted proxy, so the hop count is wrong
        return str(chain[0])
    return own


def prefix(ip: Optional[str]) -> str:
    """Only the first part of an address, for records and alerts (first two octets for IPv4, /32 for IPv6)."""
    a = parse(ip)
    if a is None:
        return ""
    if a.version == 4:
        o = str(a).split(".")
        return f"{o[0]}.{o[1]}.x.x"
    net = ipaddress.ip_network(f"{a}/32", strict=False)
    return f"{net.network_address}/32"
