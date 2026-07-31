"""SSRF guard.

The engine fetches URLs a user typed, from inside our own network. These tests
pin the boundary: anything that resolves somewhere internal must be refused
before a socket is opened.
"""

from __future__ import annotations

import pytest

from app.audit.fetcher import UnsafeURLError, assert_public_address, validate_url
from app.core.config import settings


@pytest.fixture(autouse=True)
def _enforce_production_rules(monkeypatch):
    """The dev escape hatch must never be on while these run."""
    monkeypatch.setattr(settings, "allow_private_network_fetch", False)


class TestAddressChecks:
    @pytest.mark.parametrize(
        "address",
        [
            "127.0.0.1",       # loopback
            "127.1.2.3",       # the whole 127/8 block
            "0.0.0.0",         # unspecified
            "10.0.0.5",        # RFC1918
            "172.16.4.9",      # RFC1918
            "192.168.1.1",     # RFC1918
            "169.254.169.254", # cloud metadata - the classic SSRF target
            "169.254.1.1",     # link-local generally
            "::1",             # IPv6 loopback
            "fc00::1",         # IPv6 unique-local
            "fe80::1",         # IPv6 link-local
            "::ffff:127.0.0.1", # IPv4 loopback smuggled inside IPv6
            "::ffff:10.0.0.1",  # IPv4 private smuggled inside IPv6
        ],
    )
    def test_internal_addresses_are_refused(self, address: str):
        with pytest.raises(UnsafeURLError):
            assert_public_address(address)

    @pytest.mark.parametrize("address", ["8.8.8.8", "1.1.1.1", "93.184.216.34", "2606:4700::1111"])
    def test_public_addresses_are_allowed(self, address: str):
        assert_public_address(address)

    def test_garbage_is_refused(self):
        with pytest.raises(UnsafeURLError):
            assert_public_address("not-an-ip")


class TestUrlValidation:
    @pytest.mark.parametrize(
        "url",
        [
            "file:///etc/passwd",
            "gopher://example.com/",
            "ftp://example.com/",
            "data:text/html,<script>alert(1)</script>",
            "javascript:alert(1)",
        ],
    )
    def test_non_http_schemes_are_refused(self, url: str):
        with pytest.raises(UnsafeURLError, match="http"):
            validate_url(url)

    def test_embedded_credentials_are_refused(self):
        # user:pass@host is a classic way to disguise the real target.
        with pytest.raises(UnsafeURLError, match="credentials"):
            validate_url("http://user:password@example.com/")

    @pytest.mark.parametrize("port", [22, 3306, 5432, 6379, 9200, 11211, 25])
    def test_non_web_ports_are_refused(self, port: int):
        with pytest.raises(UnsafeURLError, match="port"):
            validate_url(f"http://example.com:{port}/")

    @pytest.mark.parametrize("port", [80, 443, 8080, 8443])
    def test_standard_web_ports_are_allowed(self, port: int):
        # example.com resolves publicly; this only needs the port to pass.
        validate_url(f"https://example.com:{port}/")

    def test_loopback_by_name_is_refused(self):
        with pytest.raises(UnsafeURLError):
            validate_url("http://localhost/")

    def test_loopback_by_address_is_refused(self):
        with pytest.raises(UnsafeURLError):
            validate_url("http://127.0.0.1/")

    def test_metadata_endpoint_is_refused(self):
        with pytest.raises(UnsafeURLError):
            validate_url("http://169.254.169.254/latest/meta-data/")

    def test_unresolvable_host_is_refused(self):
        with pytest.raises(UnsafeURLError, match="resolve"):
            validate_url("http://this-domain-should-never-resolve-xyzzy.invalid/")

    def test_missing_hostname_is_refused(self):
        with pytest.raises(UnsafeURLError):
            validate_url("http:///just-a-path")

    def test_a_public_url_passes(self):
        assert validate_url("https://example.com/") == "https://example.com/"


class TestDevelopmentEscapeHatch:
    def test_private_addresses_allowed_only_when_explicitly_enabled(self, monkeypatch):
        """The flag exists for local development and is refused in production
        by Settings.validate_for_production()."""
        monkeypatch.setattr(settings, "allow_private_network_fetch", True)
        assert_public_address("127.0.0.1")  # does not raise

    def test_production_config_check_rejects_the_flag(self, monkeypatch):
        monkeypatch.setattr(settings, "environment", "production")
        monkeypatch.setattr(settings, "allow_private_network_fetch", True)

        problems = settings.validate_for_production()

        assert any("ALLOW_PRIVATE_NETWORK_FETCH" in problem for problem in problems)
