"""Restricted HTTPS acquisition with DNS pinning. No proxies, redirects or credentials."""

from __future__ import annotations

import hashlib
import http.client
import ipaddress
import json
import socket
import ssl
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from dataclasses import dataclass
from threading import BoundedSemaphore, Event, Timer
from urllib.parse import quote, urlsplit


class AcquisitionError(ValueError):
    pass


def approved_target(url: str, hosts: list[str]) -> tuple[str, str]:
    try:
        parsed = urlsplit(url)
        host = (parsed.hostname or "").encode("idna").decode().lower()
        port = parsed.port
    except (ValueError, UnicodeError):
        raise AcquisitionError("ACQUISITION_URL_REJECTED") from None
    if (
        len(url) > 2000
        or any(ord(c) < 33 for c in url)
        or "\\" in url
        or parsed.scheme != "https"
        or not host
        or host not in hosts
        or parsed.username
        or parsed.password
        or port not in {None, 443}
        or parsed.fragment
    ):
        raise AcquisitionError("ACQUISITION_URL_REJECTED")
    return host, (parsed.path or "/") + ("?" + parsed.query if parsed.query else "")


_dns_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="cf-dns")
_dns_slots = BoundedSemaphore(4)


def public_addresses(host: str, timeout: float = 5) -> list[str]:
    if not _dns_slots.acquire(blocking=False):
        raise AcquisitionError("ACQUISITION_DNS_BUSY")
    future = _dns_pool.submit(socket.getaddrinfo, host, 443, type=socket.SOCK_STREAM)
    future.add_done_callback(lambda _: _dns_slots.release())
    try:
        values = sorted({str(info[4][0]) for info in future.result(timeout=timeout)})
    except (OSError, FutureTimeout):
        future.cancel()
        raise AcquisitionError("ACQUISITION_DNS_FAILED") from None
    if not values:
        raise AcquisitionError("ACQUISITION_DNS_FAILED")
    for value in values:
        ip = ipaddress.ip_address(value)
        transition = isinstance(ip, ipaddress.IPv6Address) and (
            ip.ipv4_mapped is not None
            or ip.sixtofour is not None
            or ip.teredo is not None
            or ip in ipaddress.ip_network("64:ff9b::/96")
            or ip in ipaddress.ip_network("64:ff9b:1::/48")
        )
        if (
            not ip.is_global
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
            or transition
            or value == "168.63.129.16"
        ):
            raise AcquisitionError("ACQUISITION_ADDRESS_REJECTED")
    return values


@dataclass(frozen=True)
class Fetched:
    content: bytes
    media_type: str
    sha256: str
    address: str
    elapsed_ms: float


class SafeFetcher:
    def __init__(self, hosts: list[str], timeout: float = 15, max_bytes: int = 20 * 1024 * 1024):
        self.hosts = hosts
        self.timeout = timeout
        self.max_bytes = max_bytes

    def get(self, url: str) -> Fetched:
        started = time.monotonic()
        host, path = approved_target(url, self.hosts)

        def remaining() -> float:
            value = self.timeout - (time.monotonic() - started)
            if value <= 0:
                raise AcquisitionError("ACQUISITION_TIMEOUT")
            return value

        addresses = public_addresses(host, timeout=min(5, remaining()))
        # Use the validated numeric address exactly once. TLS still authenticates
        # the original hostname; no second DNS lookup or automatic redirect exists.
        connection = http.client.HTTPSConnection(host, timeout=remaining())
        raw: socket.socket | None = None
        transport: socket.socket | None = None
        response: http.client.HTTPResponse | None = None
        deadline_timer: Timer | None = None
        expired = Event()

        def expire() -> None:
            expired.set()
            current = connection.sock or raw or transport
            if current:
                try:
                    current.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass

        try:
            raw = socket.create_connection((addresses[0], 443), timeout=remaining())
            if raw.getpeername()[0] not in addresses:
                raise AcquisitionError("ACQUISITION_ADDRESS_REJECTED")
            deadline_timer = Timer(remaining(), expire)
            deadline_timer.daemon = True
            deadline_timer.start()
            raw.settimeout(remaining())
            connection.sock = ssl.create_default_context().wrap_socket(raw, server_hostname=host)
            raw = None  # HTTPSConnection owns the TLS socket now.
            connection.request(
                "GET",
                path,
                headers={
                    "Host": host,
                    "Accept-Encoding": "identity",
                    "User-Agent": "CorpusFlow/0.1 (local research acquisition)",
                },
            )
            connection.sock.settimeout(remaining())
            transport = connection.sock
            response = connection.getresponse()
            if 300 <= response.status < 400:
                raise AcquisitionError("ACQUISITION_REDIRECT_REJECTED")
            if response.status != 200:
                raise AcquisitionError("ACQUISITION_HTTP_FAILED")
            if response.getheader("Content-Encoding", "identity").lower() != "identity":
                raise AcquisitionError("ACQUISITION_ENCODING_REJECTED")
            length = response.getheader("Content-Length")
            if length is not None and (
                not length.isascii() or not length.isdigit() or len(length) > 12
            ):
                raise AcquisitionError("ACQUISITION_LENGTH_INVALID")
            if length and int(length) > self.max_bytes:
                raise AcquisitionError("ACQUISITION_SIZE_LIMIT")
            chunks = []
            total = 0
            while not response.isclosed():
                transport.settimeout(remaining())
                block = response.read1(min(64 * 1024, self.max_bytes + 1 - total))
                if not block:
                    break
                chunks.append(block)
                total += len(block)
                if total > self.max_bytes:
                    raise AcquisitionError("ACQUISITION_SIZE_LIMIT")
            if length is not None and total != int(length):
                raise AcquisitionError("ACQUISITION_TRUNCATED")
            remaining()
            content = b"".join(chunks)
            return Fetched(
                content,
                response.getheader("Content-Type", "").split(";")[0].strip(),
                hashlib.sha256(content).hexdigest(),
                addresses[0],
                (time.monotonic() - started) * 1000,
            )
        except (OSError, ValueError, http.client.HTTPException) as exc:
            if isinstance(exc, AcquisitionError):
                raise
            raise AcquisitionError(
                "ACQUISITION_TIMEOUT"
                if expired.is_set() or isinstance(exc, TimeoutError)
                else "ACQUISITION_NETWORK_FAILED"
            ) from None
        finally:
            if deadline_timer:
                deadline_timer.cancel()
            if response:
                response.close()
            connection.close()
            if raw:
                raw.close()

    def doi(self, doi: str) -> dict[str, object]:
        import re

        if not re.fullmatch(r"10\.\d{4,9}/[^\s]{1,180}", doi):
            raise AcquisitionError("DOI_INVALID")
        result = self.get("https://api.crossref.org/works/" + quote(doi, safe=""))
        payload = json.loads(result.content)["message"]
        # Abstracts/fulltext are intentionally excluded; metadata is not a license grant.
        return {
            "doi": payload["DOI"],
            "title": payload.get("title", []),
            "publisher": payload.get("publisher"),
            "published": payload.get("published"),
            "license_claims": payload.get("license", []),
            "url": payload.get("URL"),
            "response_sha256": result.sha256,
            "purpose_grant": "NOT_GRANTED",
        }
