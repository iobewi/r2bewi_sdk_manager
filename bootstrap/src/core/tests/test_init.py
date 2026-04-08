"""Tests de non-régression pour src.core.init — hostname, DHCP range, substitute."""
from __future__ import annotations

import pytest

from src.core.init import _dhcp_range, _substitute, _HOSTNAME_RE


class TestHostnameRegex:
    def test_lowercase_accepted(self):
        assert _HOSTNAME_RE.match("r2arm01")

    def test_uppercase_rejected(self):
        assert _HOSTNAME_RE.match("R2ARM01") is None

    def test_mixed_case_rejected(self):
        assert _HOSTNAME_RE.match("R2arm01") is None

    def test_hyphen_accepted(self):
        assert _HOSTNAME_RE.match("r2-arm-01")

    def test_underscore_rejected(self):
        assert _HOSTNAME_RE.match("r2_arm01") is None

    def test_single_char_accepted(self):
        assert _HOSTNAME_RE.match("a")

    def test_starts_with_hyphen_rejected(self):
        assert _HOSTNAME_RE.match("-node") is None

    def test_ends_with_hyphen_rejected(self):
        assert _HOSTNAME_RE.match("node-") is None


class TestDhcpRange:
    def test_valid_ip(self):
        start, end = _dhcp_range("192.168.82.1")
        assert start == "192.168.82.100"
        assert end == "192.168.82.200"

    def test_different_subnet(self):
        start, end = _dhcp_range("10.0.0.1")
        assert start == "10.0.0.100"
        assert end == "10.0.0.200"

    def test_invalid_ip_raises(self):
        with pytest.raises(ValueError, match="invalide"):
            _dhcp_range("<IP>")

    def test_empty_raises(self):
        with pytest.raises(ValueError):
            _dhcp_range("")

    def test_ipv6_raises(self):
        with pytest.raises(ValueError):
            _dhcp_range("::1")


class TestSubstitute:
    def test_dhcp_only_computed_when_needed(self):
        """Pour un template sans __DHCP_START__, aucun calcul DHCP — pas de ValueError."""
        content = "server: https://__IP__:6443\n"
        # IP invalide mais pas de placeholder DHCP → pas d'erreur
        result = _substitute(content, "r2arm01", "<IP>")
        assert "<IP>" in result  # substitution __IP__ OK
        assert "__DHCP_START__" not in result

    def test_dhcp_fails_on_invalid_ip(self):
        """Template avec __DHCP_START__ + IP invalide → ValueError."""
        content = "dhcp-range=__DHCP_START__,__DHCP_END__\n"
        with pytest.raises(ValueError, match="invalide"):
            _substitute(content, "r2bewi", "<IP>")

    def test_hostname_substitution(self):
        content = "hostname: __HOSTNAME__\n"
        result = _substitute(content, "r2bewi", "192.168.82.1")
        assert "r2bewi" in result

    def test_full_substitution(self):
        content = "__HOSTNAME__ __IP__ __LAN__ __DHCP_START__ __DHCP_END__"
        result = _substitute(content, "r2bewi", "192.168.1.1")
        assert "r2bewi" in result
        assert "192.168.1.1" in result
        assert "192.168.1" in result
        assert "192.168.1.100" in result
        assert "192.168.1.200" in result
