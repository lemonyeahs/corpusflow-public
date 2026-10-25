import socket

import pytest
from corpusflow.adapters.acquisition import (
    AcquisitionError,
    SafeFetcher,
    approved_target,
    public_addresses,
)


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com/a",
        "https://example.com:444/a",
        "https://u:p@example.com/a",
        "https://example.com.evil/a",
        "https://example.com/a#b",
        "https://example.com/\r\ninject",
        "file:///etc/passwd",
        "https://example.com\\@evil.com",
    ],
)
def test_url_boundary(url):
    with pytest.raises(AcquisitionError):
        approved_target(url, ["example.com"])


@pytest.mark.parametrize(
    "address", ["127.0.0.1", "169.254.169.254", "10.0.0.1", "::1", "::ffff:127.0.0.1", "224.0.0.1"]
)
def test_dns_private_or_mixed_addresses_denied(monkeypatch, address):
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *args, **kwargs: [
            (None, None, None, None, ("93.184.215.14", 443)),
            (None, None, None, None, (address, 443)),
        ],
    )
    with pytest.raises(AcquisitionError, match="ADDRESS_REJECTED"):
        public_addresses("example.com")


def test_no_allowlist_and_invalid_doi_fail_closed():
    with pytest.raises(AcquisitionError, match="URL_REJECTED"):
        SafeFetcher([]).get("https://example.com")
    with pytest.raises(AcquisitionError, match="DOI_INVALID"):
        SafeFetcher([]).doi("invalid")


@pytest.mark.parametrize(
    "address",
    [
        "198.18.0.117",
        "168.63.129.16",
        "100.64.0.1",
        "172.16.0.1",
        "192.168.1.1",
        "fc00::1",
        "fe80::1",
        "64:ff9b::a9fe:a9fe",
        "2002:7f00:1::",
        "::ffff:8.8.8.8",
    ],
)
def test_transitional_ipv6_and_nonpublic_addresses_denied(monkeypatch, address):
    monkeypatch.setattr(
        socket, "getaddrinfo", lambda *a, **k: [(None, None, None, None, (address, 443))]
    )
    with pytest.raises(AcquisitionError, match="ADDRESS_REJECTED"):
        public_addresses("fixture.example")


def test_ordinary_public_addresses_are_not_overblocked(monkeypatch):
    values = ["8.8.8.8", "2606:4700:4700::1111"]
    monkeypatch.setattr(
        socket, "getaddrinfo", lambda *a, **k: [(None, None, None, None, (v, 443)) for v in values]
    )
    assert set(public_addresses("fixture.example")) == set(values)
