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
