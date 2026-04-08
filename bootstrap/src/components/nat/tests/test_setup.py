"""
Tests unitaires — src.nat.setup (anti-régression NAT bridge interface)

Vérifie que l'interface bridge lue depuis dnsmasq.conf est utilisée dans
la règle iptables et le unit file systemd, sans être hardcodée à 'br0'.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from src.components.nat.setup import _write_nat_service


# ── _write_nat_service ────────────────────────────────────────────────────────

class TestWriteNatService:
    def _get_unit_content(self, lan_subnet: str, bridge_iface: str, tmp_path: Path) -> str:
        unit_path = tmp_path / "r2bewi-nat.service"
        written: list[str] = []
        real_path = Path

        class FakePath:
            def __init__(self, p):
                self._p = p
            def exists(self):
                return unit_path.exists()
            def read_text(self):
                return unit_path.read_text()
            def write_text(self, content):
                written.append(content)
                unit_path.write_text(content)

        with patch("src.components.nat.setup.Path",
                   side_effect=lambda *a: FakePath(real_path(*a))
                   if a and str(a[0]) == "/etc/systemd/system/r2bewi-nat.service"
                   else real_path(*a)):
            with patch("src.components.nat.setup.ok"), patch("src.components.nat.setup.info"), \
                 patch("src.components.nat.setup.run"):
                _write_nat_service(lan_subnet, bridge_iface)

        return written[0] if written else unit_path.read_text() if unit_path.exists() else ""

    def test_custom_bridge_in_execstart(self, tmp_path):
        content = self._get_unit_content("192.168.82.0/24", "br-lan", tmp_path)
        assert "br-lan" in content, f"'br-lan' absent du unit file :\n{content}"

    def test_br0_not_hardcoded_when_custom_bridge(self, tmp_path):
        content = self._get_unit_content("192.168.82.0/24", "br-lan", tmp_path)
        assert "! -o br0" not in content, f"'br0' hardcodé dans le unit file :\n{content}"

    def test_standard_br0_still_works(self, tmp_path):
        content = self._get_unit_content("192.168.82.0/24", "br0", tmp_path)
        assert "br0" in content


# ── _configure_nat intégration légère ─────────────────────────────────────────

class TestConfigureNat:
    def test_custom_bridge_used_in_iptables_call(self, tmp_path):
        from src.components.nat.setup import _configure_nat

        (tmp_path / "dnsmasq.conf").write_text(
            "interface=br-lan\n"
            "dhcp-option=option:router,192.168.10.1\n"
        )

        iptables_calls: list[list[str]] = []

        def fake_run(cmd, **kwargs):
            if "iptables" in cmd:
                iptables_calls.append(list(cmd))
            from types import SimpleNamespace
            return SimpleNamespace(returncode=1, stdout="", stderr="")

        with patch("src.components.nat.setup.which", return_value="/usr/sbin/iptables"), \
             patch("src.components.nat.setup.run", side_effect=fake_run), \
             patch("src.components.nat.setup._write_nat_service"), \
             patch("src.components.nat.setup.ok"), \
             patch("src.components.nat.setup.info"), \
             patch.object(Path, "mkdir"), \
             patch.object(Path, "write_text"):
            _configure_nat(tmp_path)

        ipt_with_o = [c for c in iptables_calls if "!" in c and "-o" in c]
        assert ipt_with_o, "Aucune commande iptables avec -o trouvée"
        for cmd in ipt_with_o:
            o_idx = cmd.index("-o")
            iface = cmd[o_idx + 1]
            assert iface == "br-lan", f"Interface attendue 'br-lan', reçu {iface!r} dans {cmd}"
