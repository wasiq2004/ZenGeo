"""SSRF-guarded HTTP fetching for user-supplied URLs.

The audit engine fetches addresses that an unauthenticated-ish user typed in,
from inside our own network. Without a guard that is a straightforward SSRF:
`http://169.254.169.254/` reads cloud metadata, `http://postgres:5432/` probes
internal services, `http://127.0.0.1:8000/` talks to our own API.

Three layers of defence, because DNS is not trustworthy:

1. Scheme and port allow-lists reject the obviously wrong shapes.
2. Every hostname is resolved and *all* returned addresses are checked. A host
   with one public and one private A record is rejected.
3. After the socket is open, the address we actually connected to is checked
   again. This closes the DNS-rebinding window, where a name resolves to a
   public IP during validation and a private one microseconds later at connect
   time - a check-then-use race a pre-flight lookup alone cannot win.

Redirects are followed manually so every hop goes through the same checks; an
open redirect to `http://127.0.0.1/` is otherwise a bypass of steps 1 and 2.
"""

from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlparse

import httpx

from app.core.config import settings
from app.core.logging import get_logger

log = get_logger("audit.fetch")

ALLOWED_SCHEMES = {"http", "https"}
#: Standard web ports only. Anything else on a public host is far more likely
#: to be an internal service probe than a website.
ALLOWED_PORTS = {80, 443, 8080, 8443}
MAX_REDIRECTS = 5


class UnsafeURLError(Exception):
    """The URL points somewhere the audit engine must not fetch."""


class FetchError(Exception):
    """The URL was safe but could not be retrieved."""


@dataclass(slots=True)
class FetchResult:
    url: str
    final_url: str
    status_code: int
    content_type: str
    text: str
    ok: bool
    elapsed_ms: int
    truncated: bool = False
    redirected_to_https: bool = False
    error: str | None = None
    headers: dict[str, str] = field(default_factory=dict)


def _is_disallowed_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> str | None:
    """Return a reason string when this address must not be contacted."""
    if ip.is_loopback:
        return "loopback address"
    if ip.is_private:
        return "private network address"
    if ip.is_link_local:
        # Covers 169.254.0.0/16, which is where cloud metadata services live.
        return "link-local address"
    if ip.is_reserved:
        return "reserved address"
    if ip.is_multicast:
        return "multicast address"
    if ip.is_unspecified:
        return "unspecified address"
    if isinstance(ip, ipaddress.IPv6Address):
        # An attacker can smuggle a private IPv4 inside an IPv6 wrapper.
        mapped = ip.ipv4_mapped or (ip.sixtofour if ip.sixtofour else None)
        if mapped is not None and _is_disallowed_ip(mapped):
            return "IPv6-wrapped private address"
    return None


def assert_public_address(ip_text: str) -> None:
    try:
        ip = ipaddress.ip_address(ip_text)
    except ValueError as exc:
        raise UnsafeURLError(f"{ip_text} is not a valid IP address") from exc

    if settings.allow_private_network_fetch:
        return  # development escape hatch; refused at boot in production

    reason = _is_disallowed_ip(ip)
    if reason:
        raise UnsafeURLError(f"Refusing to fetch {ip} - {reason}")


def validate_url(raw_url: str) -> str:
    """Full pre-flight check. Returns the URL to fetch, or raises UnsafeURLError."""
    parsed = urlparse(raw_url)

    if parsed.scheme not in ALLOWED_SCHEMES:
        raise UnsafeURLError(f"Only http and https are supported (got '{parsed.scheme}')")
    hostname = parsed.hostname
    if not hostname:
        raise UnsafeURLError("That URL has no hostname")
    if parsed.username or parsed.password:
        # user:pass@host is a classic way to disguise the real target.
        raise UnsafeURLError("URLs with embedded credentials are not accepted")

    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    if port not in ALLOWED_PORTS:
        raise UnsafeURLError(f"Port {port} is not a standard web port")

    try:
        infos = socket.getaddrinfo(hostname, port, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise UnsafeURLError(f"Could not resolve {hostname}") from exc

    if not infos:
        raise UnsafeURLError(f"Could not resolve {hostname}")

    # Every address must be safe. One public and one private record is a
    # deliberate bypass attempt, not a misconfiguration to tolerate.
    for info in infos:
        # sockaddr is (host, port) for IPv4 and (host, port, flow, scope) for
        # IPv6; the host is always the first element.
        assert_public_address(str(info[4][0]))

    return raw_url


def _peer_address(response: httpx.Response) -> str | None:
    """The IP we actually connected to, for the post-connection re-check."""
    stream = response.extensions.get("network_stream")
    if stream is None:
        return None
    try:
        peer = stream.get_extra_info("server_addr")
    except Exception:
        return None
    if isinstance(peer, tuple) and peer:
        return str(peer[0])
    return None


class SafeFetcher:
    """Async HTTP client that refuses to touch internal addresses."""

    def __init__(
        self,
        *,
        timeout: float | None = None,
        max_bytes: int | None = None,
        user_agent: str | None = None,
    ) -> None:
        self.timeout = timeout or settings.fetch_timeout_seconds
        self.max_bytes = max_bytes or settings.fetch_max_bytes
        self.user_agent = user_agent or settings.user_agent
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> SafeFetcher:
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(self.timeout, connect=min(self.timeout, 10.0)),
            # Redirects are followed by hand so each hop is re-validated.
            follow_redirects=False,
            headers={
                "User-Agent": self.user_agent,
                "Accept": "text/html,application/xhtml+xml,text/plain,*/*",
                "Accept-Language": "en",
            },
            # A site with a broken certificate is a finding, not a reason to
            # disable verification.
            verify=True,
        )
        return self

    async def __aexit__(self, *_exc: object) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def fetch(self, url: str) -> FetchResult:
        """Fetch a URL, following safe redirects. Never raises for HTTP status."""
        if self._client is None:
            raise RuntimeError("SafeFetcher must be used as an async context manager")

        started_scheme = urlparse(url).scheme
        current = url
        redirected_to_https = False

        for hop in range(MAX_REDIRECTS + 1):
            try:
                safe_url = validate_url(current)
            except UnsafeURLError as exc:
                return FetchResult(
                    url=url,
                    final_url=current,
                    status_code=0,
                    content_type="",
                    text="",
                    ok=False,
                    elapsed_ms=0,
                    error=str(exc),
                )

            try:
                request = self._client.build_request("GET", safe_url)
                response = await self._client.send(request, stream=True)
            except httpx.HTTPError as exc:
                return FetchResult(
                    url=url,
                    final_url=current,
                    status_code=0,
                    content_type="",
                    text="",
                    ok=False,
                    elapsed_ms=0,
                    error=f"{type(exc).__name__}: {exc}",
                )

            # Post-connection re-check: defeats DNS rebinding between the
            # pre-flight lookup and the actual TCP connect.
            peer = _peer_address(response)
            if peer is not None:
                try:
                    assert_public_address(peer)
                except UnsafeURLError as exc:
                    await response.aclose()
                    log.warning("ssrf_rebind_blocked", url=current, peer=peer)
                    return FetchResult(
                        url=url,
                        final_url=current,
                        status_code=0,
                        content_type="",
                        text="",
                        ok=False,
                        elapsed_ms=0,
                        error=f"Connection blocked after DNS resolution: {exc}",
                    )

            if response.is_redirect and hop < MAX_REDIRECTS:
                location = response.headers.get("location", "")
                await response.aclose()
                if not location:
                    break
                current = urljoin(current, location)
                if started_scheme == "http" and urlparse(current).scheme == "https":
                    redirected_to_https = True
                continue

            body = bytearray()
            truncated = False
            try:
                async for chunk in response.aiter_bytes():
                    body.extend(chunk)
                    if len(body) >= self.max_bytes:
                        # Stop reading rather than buffering an unbounded body.
                        truncated = True
                        break
            except httpx.HTTPError as exc:
                await response.aclose()
                return FetchResult(
                    url=url,
                    final_url=str(response.url),
                    status_code=response.status_code,
                    content_type=response.headers.get("content-type", ""),
                    text="",
                    ok=False,
                    elapsed_ms=int(response.elapsed.total_seconds() * 1000),
                    error=f"Read failed: {type(exc).__name__}: {exc}",
                )
            finally:
                await response.aclose()

            encoding = response.charset_encoding or "utf-8"
            try:
                text = bytes(body).decode(encoding, errors="replace")
            except LookupError:
                text = bytes(body).decode("utf-8", errors="replace")

            return FetchResult(
                url=url,
                final_url=str(response.url),
                status_code=response.status_code,
                content_type=response.headers.get("content-type", ""),
                text=text,
                ok=200 <= response.status_code < 300,
                elapsed_ms=int(response.elapsed.total_seconds() * 1000),
                truncated=truncated,
                redirected_to_https=redirected_to_https,
                headers={k.lower(): v for k, v in response.headers.items()},
            )

        return FetchResult(
            url=url,
            final_url=current,
            status_code=0,
            content_type="",
            text="",
            ok=False,
            elapsed_ms=0,
            error=f"Too many redirects (more than {MAX_REDIRECTS})",
        )
