"""
Tests unitaires — src.components.wireguard.peer
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.components.wireguard.peer import (
    _next_peer_ip,
    _read_lan_from_wg_conf,
    _build_client_conf,
)


class TestNextPeerIp:
    """Tests pour _next_peer_ip()."""

    def test_first_peer_gets_dot_two(self):
        """Sans peers existants, le premier obtient 10.8.0.2."""
        conf = "[Interface]\nAddress = 10.8.0.1/24\n"
        assert _next_peer_ip(conf) == "10.8.0.2"

    def test_skips_used_ips(self):
        """Les IPs déjà allouées sont ignorées."""
        conf = (
            "[Interface]\nAddress = 10.8.0.1/24\n"
            "[Peer]\nAllowedIPs = 10.8.0.2/32\n"
            "[Peer]\nAllowedIPs = 10.8.0.3/32\n"
        )
        assert _next_peer_ip(conf) == "10.8.0.4"

    def test_handles_non_contiguous_ips(self):
        """Les trous dans l'allocation sont comblés."""
        conf = (
            "[Interface]\n"
            "[Peer]\nAllowedIPs = 10.8.0.2/32\n"
            "[Peer]\nAllowedIPs = 10.8.0.4/32\n"
        )
        assert _next_peer_ip(conf) == "10.8.0.3"

    def test_subnet_full_raises(self):
        """Si tous les IPs sont utilisés, RuntimeError est levée."""
        used = "".join(f"[Peer]\nAllowedIPs = 10.8.0.{i}/32\n" for i in range(2, 255))
        conf = "[Interface]\n" + used
        with pytest.raises(RuntimeError, match="saturé"):
            _next_peer_ip(conf)


class TestReadLanFromWgConf:
    """Tests pour _read_lan_from_wg_conf()."""

    def test_reads_lan_from_postrouting(self):
        """Extrait le subnet LAN depuis la règle POSTROUTING."""
        conf = (
            "PostUp = iptables -t nat -A POSTROUTING -s 10.8.0.0/24 -o eth0 -j MASQUERADE; "
            "iptables -t nat -A POSTROUTING -s 192.168.82.0/24 -o eth0 -j MASQUERADE\n"
        )
        # The regex finds the first non-10.8.x match
        result = _read_lan_from_wg_conf(conf)
        assert result == "192.168.82.0/24"

    def test_default_when_no_postrouting(self):
        """Retourne le subnet par défaut si pas de POSTROUTING."""
        conf = "[Interface]\nPrivateKey = abc\n"
        assert _read_lan_from_wg_conf(conf) == "192.168.82.0/24"

    def test_skips_vpn_subnet(self):
        """Ne retourne pas le subnet VPN (10.8.x)."""
        conf = "PostUp = iptables -t nat -A POSTROUTING -s 10.8.0.0/24 -o eth0 -j MASQUERADE"
        # Only 10.8.x present → default
        assert _read_lan_from_wg_conf(conf) == "192.168.82.0/24"


class TestBuildClientConf:
    """Tests pour _build_client_conf()."""

    def test_contains_private_key(self):
        conf = _build_client_conf(
            peer_name="mydev",
            peer_privkey="MYPRIVKEY",
            peer_ip="10.8.0.2",
            server_pubkey="SERVERPUBKEY",
            endpoint="1.2.3.4",
            port=51820,
            lan="192.168.82.0/24",
        )
        assert "PrivateKey = MYPRIVKEY" in conf

    def test_contains_endpoint(self):
        conf = _build_client_conf(
            peer_name="mydev",
            peer_privkey="MYPRIVKEY",
            peer_ip="10.8.0.2",
            server_pubkey="SERVERPUBKEY",
            endpoint="1.2.3.4",
            port=51820,
            lan="192.168.82.0/24",
        )
        assert "Endpoint   = 1.2.3.4:51820" in conf

    def test_placeholder_when_no_endpoint(self):
        conf = _build_client_conf(
            peer_name="mydev",
            peer_privkey="MYPRIVKEY",
            peer_ip="10.8.0.2",
            server_pubkey="SERVERPUBKEY",
            endpoint=None,
            port=51820,
            lan="192.168.82.0/24",
        )
        assert "<BASTION_IP>:51820" in conf

    def test_dns_hook_uses_postup(self):
        conf = _build_client_conf(
            peer_name="mydev",
            peer_privkey="MYPRIVKEY",
            peer_ip="10.8.0.2",
            server_pubkey="SERVERPUBKEY",
            endpoint="1.2.3.4",
            port=51820,
            lan="192.168.82.0/24",
            dns_hook=True,
        )
        assert "PostUp" in conf
        assert "PreDown" in conf
        assert "DNS        =" not in conf

    def test_no_dns_hook_uses_dns_line(self):
        conf = _build_client_conf(
            peer_name="mydev",
            peer_privkey="MYPRIVKEY",
            peer_ip="10.8.0.2",
            server_pubkey="SERVERPUBKEY",
            endpoint="1.2.3.4",
            port=51820,
            lan="192.168.82.0/24",
            dns_hook=False,
        )
        assert "DNS        = 10.8.0.1" in conf

    def test_contains_peer_section(self):
        conf = _build_client_conf(
            peer_name="mydev",
            peer_privkey="MYPRIVKEY",
            peer_ip="10.8.0.2",
            server_pubkey="SERVERPUBKEY",
            endpoint="1.2.3.4",
            port=51820,
            lan="192.168.82.0/24",
        )
        assert "[Peer]" in conf
        assert "PublicKey  = SERVERPUBKEY" in conf
        assert "PersistentKeepalive = 25" in conf


class TestExecuteFunction:
    """Tests pour _execute() — flux principal avec WireGuard mocké."""

    def _setup_wg_files(self, wg_dir):
        """Crée les fichiers WireGuard de base."""
        (wg_dir / "wg0.pub").write_text("SERVERPUBKEY\n")
        (wg_dir / "wg0.conf").write_text(
            "[Interface]\nAddress = 10.8.0.1/24\nPrivateKey = SERVERPRIVKEY\n"
            "PostUp = iptables -t nat -A POSTROUTING -s 10.8.0.0/24 -o eth0 -j MASQUERADE; "
            "iptables -t nat -A POSTROUTING -s 192.168.82.0/24 -o eth0 -j MASQUERADE\n"
        )

    def test_execute_adds_peer_block(self, tmp_path):
        """_execute() ajoute un bloc [Peer] dans wg0.conf."""
        wg_dir = tmp_path / "wireguard"
        wg_dir.mkdir()
        self._setup_wg_files(wg_dir)

        conf_file = wg_dir / "wg0.conf"
        pub_file = wg_dir / "wg0.pub"

        run_call_count = [0]

        def fake_run(cmd, **kwargs):
            run_call_count[0] += 1
            result = MagicMock()
            result.returncode = 1  # wg show fails (interface not active)
            if cmd == ["wg", "genkey"]:
                result.returncode = 0
                result.stdout = "PEERPRIVKEY"
            elif cmd == ["wg", "pubkey"]:
                result.returncode = 0
                result.stdout = "PEERPUBKEY"
            else:
                result.stdout = ""
            return result

        real_path = Path

        def path_factory(*args):
            path_str = str(real_path(*args))
            if path_str == str(wg_dir / "wg0.conf"):
                return conf_file
            if path_str == str(wg_dir / "wg0.pub"):
                return pub_file
            return real_path(*args)

        with patch("src.components.wireguard.peer._run_cmd", side_effect=fake_run), \
             patch("src.components.wireguard.peer._WG_CONF", conf_file), \
             patch("src.components.wireguard.peer._WG_PUB", pub_file):
            from src.components.wireguard.peer import _execute
            _execute(peer_name="testpeer", endpoint="1.2.3.4", port=51820)

        content = conf_file.read_text()
        assert "[Peer]" in content
        assert "PEERPUBKEY" in content

    def test_execute_saves_out_file(self, tmp_path):
        """_execute() sauvegarde la conf client dans --out si fourni."""
        wg_dir = tmp_path / "wireguard"
        wg_dir.mkdir()
        self._setup_wg_files(wg_dir)
        conf_file = wg_dir / "wg0.conf"
        pub_file = wg_dir / "wg0.pub"
        out_file = tmp_path / "client.conf"

        def fake_run(cmd, **kwargs):
            result = MagicMock()
            result.returncode = 1
            if cmd == ["wg", "genkey"]:
                result.returncode = 0
                result.stdout = "PEERPRIVKEY2"
            elif cmd == ["wg", "pubkey"]:
                result.returncode = 0
                result.stdout = "PEERPUBKEY2"
            else:
                result.stdout = ""
            return result

        with patch("src.components.wireguard.peer._run_cmd", side_effect=fake_run), \
             patch("src.components.wireguard.peer._WG_CONF", conf_file), \
             patch("src.components.wireguard.peer._WG_PUB", pub_file):
            from src.components.wireguard.peer import _execute
            _execute(peer_name="testpeer2", endpoint="5.6.7.8", port=51820, out=str(out_file))

        assert out_file.exists()
        content = out_file.read_text()
        assert "PrivateKey = PEERPRIVKEY2" in content
