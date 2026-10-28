#!/usr/bin/env python3
"""stack-watch HTTP guardrails, shared by every script that fetches.

    text, final_url = open_url(url, timeout, headers=None, limit=5_000_000)

Rules enforced on the first request and on every redirect hop:

  * http and https only (no file://, ftp://, data:, ...)
  * no credentials in the URL (user:pass@host)
  * no private, loopback, link-local, multicast, or reserved addresses
    unless ALLOW_PRIVATE is set (the scripts expose --allow-private-hosts);
    this covers 10/8, 172.16/12, 192.168/16, 127/8, 169.254/16 and the
    cloud metadata address, and their IPv6 equivalents
  * at most 5 redirects, followed manually so the rules apply each time
  * the Authorization header is dropped when a redirect leaves the host it
    was meant for
  * the body is read up to `limit` bytes; a larger response is an error,
    not a truncation, so a feed cannot exhaust memory

Everything raises ValueError (policy) or urllib.error.URLError (network).
Standard library only.
"""

import ipaddress
import socket
import urllib.error
import urllib.parse
import urllib.request

USER_AGENT = "stack-watch/1.3 (+https://github.com/raz-app-io/stack-watch)"
REDIRECT_CODES = {301, 302, 303, 307, 308}
MAX_HOPS = 5
ALLOW_PRIVATE = False  # set True (or pass allow_private=True) for self-hosted targets


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # surface 3xx as HTTPError so open_url can police the hop


_OPENER = urllib.request.build_opener(_NoRedirect)


def is_private_host(host):
    """True when the host name or literal address resolves to a non-public
    address. A name that does not resolve counts as private (fail closed)."""
    host = host.strip("[]")
    try:
        addrs = {ipaddress.ip_address(host)}
    except ValueError:
        try:
            addrs = {ipaddress.ip_address(info[4][0]) for info in
                     socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)}
        except (socket.gaierror, UnicodeError, OSError):
            return True
    return any(a.is_private or a.is_loopback or a.is_link_local or a.is_multicast
               or a.is_reserved or a.is_unspecified for a in addrs)


def check_url(url, allow_private=None):
    """Raise ValueError unless the URL may be fetched. Returns the parsed URL."""
    parts = urllib.parse.urlsplit(str(url or "").strip())
    if parts.scheme not in ("http", "https"):
        raise ValueError(f"refusing {parts.scheme or 'schemeless'} URL: only http(s) is fetched")
    if not parts.hostname:
        raise ValueError("refusing URL without a host")
    if parts.username is not None or parts.password is not None:
        raise ValueError("refusing URL with embedded credentials")
    allow = ALLOW_PRIVATE if allow_private is None else allow_private
    if not allow and is_private_host(parts.hostname):
        raise ValueError(f"refusing private or unresolvable host {parts.hostname}"
                         " (use --allow-private-hosts to permit)")
    return parts


def open_url(url, timeout, headers=None, limit=5_000_000, allow_private=None):
    """GET a URL under the rules above. Returns (text, final_url)."""
    headers = dict(headers or {})
    headers.setdefault("User-Agent", USER_AGENT)
    origin_host = check_url(url, allow_private).netloc.lower()
    current = url
    for _ in range(MAX_HOPS + 1):
        parts = check_url(current, allow_private)
        send = dict(headers)
        if parts.netloc.lower() != origin_host:
            send.pop("Authorization", None)  # never carry a token to another host
        req = urllib.request.Request(current, headers=send)
        try:
            with _OPENER.open(req, timeout=timeout) as resp:
                data = resp.read(limit + 1)
                if len(data) > limit:
                    raise ValueError(f"response larger than {limit} bytes")
                return data.decode("utf-8", errors="replace"), resp.geturl()
        except urllib.error.HTTPError as e:
            target = e.headers.get("Location") if e.headers else None
            if e.code in REDIRECT_CODES and target:
                current = urllib.parse.urljoin(current, target)
                continue
            raise
    raise urllib.error.URLError(f"too many redirects (more than {MAX_HOPS})")
