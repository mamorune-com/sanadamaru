"""送り元の番号（IP アドレス）の読み方と、締め出してよい番号かの判断。

締め出しで、いちばん大事なのは「無関係な人を巻き込まない」ことです（docs/lines.md の 5）。
そのため、確かでない番号は締め出しません。

- Cloudflare 自身の番号：大勢の利用者の通り道です。ここを締め出すと、全員を締め出します。
- 公開されていない番号（社内・家庭内・CGNAT・ループバックなど）：前に立つ仕組み（ロードバランサーなど）の
  番号であることが多く、ここを締め出すと、やはり全員を締め出します。
"""
from __future__ import annotations

import ipaddress
from typing import Mapping, Optional, Union

_Address = Union[ipaddress.IPv4Address, ipaddress.IPv6Address]

# Cloudflare が公表している番号の範囲（https://www.cloudflare.com/ips/ ・2026-10 時点）。
# 変わることがあるため、時々見直してください。
CLOUDFLARE_NETWORKS = tuple(ipaddress.ip_network(n) for n in (
    "173.245.48.0/20", "103.21.244.0/22", "103.22.200.0/22", "103.31.4.0/22", "141.101.64.0/18",
    "108.162.192.0/18", "190.93.240.0/20", "188.114.96.0/20", "197.234.240.0/22", "198.41.128.0/17",
    "162.158.0.0/15", "104.16.0.0/13", "104.24.0.0/14", "172.64.0.0/13", "131.0.72.0/22",
    "2400:cb00::/32", "2606:4700::/32", "2803:f800::/32", "2405:b500::/32", "2405:8100::/32",
    "2a06:98c0::/29", "2c0f:f248::/32",
))


def parse(value: Optional[str]) -> Optional[_Address]:
    """番号として読めれば返す。`1.2.3.4:5678`・`[2001:db8::1]:443` のようにポートが付いていても読む。"""
    s = (value or "").strip()
    if not s:
        return None
    if s.startswith("["):                      # [IPv6]:port
        s = s[1:].split("]", 1)[0]
    elif s.count(":") == 1:                    # IPv4:port
        s = s.split(":", 1)[0]
    try:
        a = ipaddress.ip_address(s)
    except ValueError:
        return None
    if isinstance(a, ipaddress.IPv6Address) and a.ipv4_mapped is not None:
        return a.ipv4_mapped                   # ::ffff:1.2.3.4 は 1.2.3.4 とみなす
    return a


def is_cloudflare(ip: Optional[str]) -> bool:
    a = parse(ip)
    return a is not None and any(a.version == n.version and a in n for n in CLOUDFLARE_NETWORKS)


def banable(ip: Optional[str]) -> bool:
    """締め出してよい番号か。公開されている（global）番号で、Cloudflare 自身ではない時だけ。"""
    a = parse(ip)
    if a is None or not a.is_global or a.is_multicast:
        return False
    return not is_cloudflare(str(a))


def client_ip(mode: str, headers: Mapping[str, str], peer: Optional[str], trusted_hops: int = 1) -> str:
    """締め出しと記録に使う送り元の番号。読めない時は空の文字列。

    - direct：直接つないできた相手（前に何も立っていない時）
    - cloudflare：Cloudflare が書く `CF-Connecting-IP`（Cloudflare が上書きするので、呼び手は偽れない）。
      Cloudflare を通らずに届く構成では使わないでください（呼び手が自由に書けてしまいます）。
    - x-forwarded-for：`X-Forwarded-For` の右から trusted_hops 番目（前に立つ仕組みが足した側）。
      左側は呼び手が自由に書けるので、決して使いません。
    """
    if mode == "cloudflare":
        a = parse(headers.get("cf-connecting-ip"))
        if a is not None:
            return str(a)
    elif mode == "x-forwarded-for":
        parts = [p.strip() for p in (headers.get("x-forwarded-for") or "").split(",") if p.strip()]
        if parts:
            a = parse(parts[max(len(parts) - int(trusted_hops), 0)])
            if a is not None:
                return str(a)
    a = parse(peer)
    return str(a) if a is not None else ""


def prefix(ip: Optional[str]) -> str:
    """記録や知らせに出す、番号の頭だけ（IPv4 は上2つ・IPv6 は /32）。"""
    a = parse(ip)
    if a is None:
        return ""
    if a.version == 4:
        o = str(a).split(".")
        return f"{o[0]}.{o[1]}.x.x"
    net = ipaddress.ip_network(f"{a}/32", strict=False)
    return f"{net.network_address}/32"
