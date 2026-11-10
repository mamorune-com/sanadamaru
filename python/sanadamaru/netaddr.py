"""送り元の番号（IP アドレス）の読み方と、締め出してよい番号かの判断。

締め出しで、いちばん大事なのは「無関係な人を巻き込まない」ことです（docs/lines.md の 5）。
そのため、確かでない番号は締め出しません。

- Cloudflare 自身の番号：大勢の利用者の通り道です。ここを締め出すと、全員を締め出します。
- 公開されていない番号（社内・家庭内・CGNAT・ループバックなど）：前に立つ仕組み（ロードバランサーなど）の
  番号であることが多く、ここを締め出すと、やはり全員を締め出します。
"""
from __future__ import annotations

import ipaddress
import re
from typing import Iterable, Mapping, Optional, Sequence, Tuple, Union

_Address = Union[ipaddress.IPv4Address, ipaddress.IPv6Address]
_Network = Union[ipaddress.IPv4Network, ipaddress.IPv6Network]
_IP_CHARS = re.compile(r"[0-9A-Fa-f:.]+")   # 番号に使う文字だけ（`%scope` などの飾りは受け付けない）

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
    if not _IP_CHARS.fullmatch(s):             # `fe80::1%eth0` のような飾りや、制御文字が混ざった値は読まない
        return None
    try:
        a = ipaddress.ip_address(s)
    except ValueError:
        return None
    if isinstance(a, ipaddress.IPv6Address) and a.ipv4_mapped is not None:
        return a.ipv4_mapped                   # ::ffff:1.2.3.4 は 1.2.3.4 とみなす
    return a


def networks(values: Iterable[str]) -> Tuple[_Network, ...]:
    """`10.0.0.0/8` のような範囲の一覧を読む。読めない範囲があれば ValueError（まちがった設定では動かさない）。

    `::ffff:1.2.3.0/120` のような「IPv6 の形で書いた IPv4 の範囲」は、IPv4 の範囲（`1.2.3.0/24`）にも直して持ちます。
    番号の方は parse() が `::ffff:1.2.3.4` を `1.2.3.4` に直すので、範囲も同じ形にしないと一致しません。
    """
    out = []
    for v in values:
        try:
            n = ipaddress.ip_network(str(v).strip(), strict=False)
        except ValueError:
            raise ValueError(f"番号の範囲として読めません：{v!r}") from None
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
    """締め出してよい番号か。公開されている（global）番号で、Cloudflare 自身ではない時だけ。"""
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
    """締め出しと記録に使う送り元の番号。確かめられない時は空の文字列（空の番号は締め出しません）。

    見出し（`CF-Connecting-IP`・`X-Forwarded-For`）は、呼び手が自由に書けます。そこで、
    直接つないできた相手（peer）が「前に立つ仕組み」だと確かめられた時だけ、見出しを読みます。
    確かめられない相手が見出しを付けてきた時は、見出しを無視して、その相手自身の番号を使います。

    - direct：直接つないできた相手（前に何も立っていない時）
    - cloudflare：`CF-Connecting-IP`。直接の相手が Cloudflare の番号（または trusted_proxies の中）の時だけ読む。
    - x-forwarded-for：`X-Forwarded-For` の右から trusted_hops 番目。直接の相手が trusted_proxies の中
      （指定が無ければ、公開されていない番号＝同じ建物の中のロードバランサーなど）の時だけ読む。
      trusted_hops が2以上の時は、間にはさまる番号も前に立つ仕組み（trusted_proxies・Cloudflare・
      指定が無ければ公開されていない番号）であることを確かめる。段数が合わない時は空にする。
      左側は呼び手が自由に書けるので、決して使いません。
    """
    p = parse(peer)
    own = str(p) if p is not None else ""
    if mode == "cloudflare":
        if not (_within(p, CLOUDFLARE_NETWORKS) or _within(p, trusted_proxies)):
            return own                         # Cloudflare を通らずに届いた。見出しは偽れるので読まない
        a = parse(headers.get("cf-connecting-ip"))
        return str(a) if a is not None else ""
    if mode == "x-forwarded-for":
        def is_proxy(a: Optional[_Address]) -> bool:
            if trusted_proxies:
                return _within(a, trusted_proxies)
            return a is not None and not a.is_global
        if not is_proxy(p):
            return own                         # 前に立つ仕組みを通らずに届いた。見出しは偽れるので読まない
        parts = [x.strip() for x in (headers.get("x-forwarded-for") or "").split(",") if x.strip()]
        hops = int(trusted_hops)
        if len(parts) < hops:
            return ""                          # 段数が合わない。左側（呼び手が書ける所）を読まない
        chain = [parse(x) for x in parts[len(parts) - hops:]]
        if any(a is None for a in chain):
            return ""
        for middle in chain[1:]:
            if not (is_proxy(middle) or _within(middle, CLOUDFLARE_NETWORKS)):
                return ""                      # 間に、前に立つ仕組みでない番号がある＝段数が合っていない
        return str(chain[0])
    return own


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
