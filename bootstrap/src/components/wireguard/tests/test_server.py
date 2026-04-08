"""
Tests unitaires — src.components.wireguard.server
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest


class TestWireguardSetup:
    """Tests pour setup() dans wireguard/server.py."""

    def _make_run_mock(self, privkey="FAKEPRIVKEY", pubkey="FAKEPUBKEY"):
        """Retourne un mock de run qui simule wg genkey/pubkey."""

        def fake_run(cmd, **kwargs):
            result = MagicMock()
            result.returncode = 0
            if cmd == ["wg", "genkey"]:
                result.stdout = privkey
            elif cmd == ["wg", "pubkey"]:
                result.stdout = pubkey
            else:
                result.stdout = ""
            return result

        return fake_run

    def test_generates_keys_if_absent(self, tmp_path):
        """Clés absentes → wg genkey + wg pubkey appelés."""
        wg_dir = tmp_path / "wireguard"
        wg_dir.mkdir()
        key_file = wg_dir / "wg0.key"
        pub_file = wg_dir / "wg0.pub"
        conf_file = wg_dir / "wg0.conf"

        run_calls = []

        def fake_run(cmd, **kwargs):
            run_calls.append(cmd)
            result = MagicMock()
            result.returncode = 0
            if cmd == ["wg", "genkey"]:
                result.stdout = "FAKEPRIVKEY"
            elif cmd == ["wg", "pubkey"]:
                result.stdout = "FAKEPUBKEY"
            else:
                result.stdout = ""
            return result

        (tmp_path / "dnsmasq.conf").write_text("interface=eth0\n")

        with patch("src.components.wireguard.server.run", side_effect=fake_run), \
             patch("src.components.wireguard.server._svc"), \
             patch("src.components.wireguard.server.add_wireguard_interface"), \
             patch("src.components.wireguard.server.read_ext_if", return_value="eth0"), \
             patch("src.components.wireguard.server.Path") as MockPath:

            real_path = Path

            def path_factory(*args):
                path_str = str(real_path(*args))
                if path_str == "/etc/wireguard":
                    return wg_dir
                if path_str == "/etc/wireguard/wg0.key":
                    return key_file
                if path_str == "/etc/wireguard/wg0.pub":
                    return pub_file
                if path_str == "/etc/wireguard/wg0.conf":
                    return conf_file
                return real_path(*args)

            MockPath.side_effect = path_factory

            from src.components.wireguard.server import setup
            setup(tmp_path)

        genkey_calls = [c for c in run_calls if c == ["wg", "genkey"]]
        pubkey_calls = [c for c in run_calls if c == ["wg", "pubkey"]]
        assert len(genkey_calls) == 1
        assert len(pubkey_calls) == 1
        assert key_file.read_text().strip() == "FAKEPRIVKEY"
        assert pub_file.read_text().strip() == "FAKEPUBKEY"

    def test_skips_key_generation_if_present(self, tmp_path):
        """Clés déjà présentes → pas d'appel wg genkey."""
        wg_dir = tmp_path / "wireguard"
        wg_dir.mkdir()
        key_file = wg_dir / "wg0.key"
        pub_file = wg_dir / "wg0.pub"
        conf_file = wg_dir / "wg0.conf"

        key_file.write_text("EXISTINGPRIVKEY\n")
        pub_file.write_text("EXISTINGPUBKEY\n")
        conf_file.write_text("[Interface]\nPrivateKey = EXISTINGPRIVKEY\n")

        run_calls = []

        def fake_run(cmd, **kwargs):
            run_calls.append(cmd)
            return MagicMock(returncode=0, stdout="")

        with patch("src.components.wireguard.server.run", side_effect=fake_run), \
             patch("src.components.wireguard.server._svc"), \
             patch("src.components.wireguard.server.add_wireguard_interface"), \
             patch("src.components.wireguard.server.read_ext_if", return_value="eth0"), \
             patch("src.components.wireguard.server.Path") as MockPath:

            real_path = Path

            def path_factory(*args):
                path_str = str(real_path(*args))
                if path_str == "/etc/wireguard":
                    return wg_dir
                if path_str == "/etc/wireguard/wg0.key":
                    return key_file
                if path_str == "/etc/wireguard/wg0.pub":
                    return pub_file
                if path_str == "/etc/wireguard/wg0.conf":
                    return conf_file
                return real_path(*args)

            MockPath.side_effect = path_factory

            from src.components.wireguard.server import setup
            setup(tmp_path)

        genkey_calls = [c for c in run_calls if c == ["wg", "genkey"]]
        assert genkey_calls == []

    def test_writes_conf_if_absent(self, tmp_path):
        """wg0.conf absent → fichier créé avec PrivateKey et PostUp."""
        wg_dir = tmp_path / "wireguard"
        wg_dir.mkdir()
        key_file = wg_dir / "wg0.key"
        pub_file = wg_dir / "wg0.pub"
        conf_file = wg_dir / "wg0.conf"

        key_file.write_text("MYPRIVKEY\n")
        pub_file.write_text("MYPUBKEY\n")
        # conf_file does NOT exist

        def fake_run(cmd, **kwargs):
            result = MagicMock()
            result.returncode = 0
            result.stdout = ""
            return result

        with patch("src.components.wireguard.server.run", side_effect=fake_run), \
             patch("src.components.wireguard.server._svc"), \
             patch("src.components.wireguard.server.add_wireguard_interface"), \
             patch("src.components.wireguard.server.read_ext_if", return_value="eth0"), \
             patch("src.components.wireguard.server.Path") as MockPath:

            real_path = Path

            def path_factory(*args):
                path_str = str(real_path(*args))
                if path_str == "/etc/wireguard":
                    return wg_dir
                if path_str == "/etc/wireguard/wg0.key":
                    return key_file
                if path_str == "/etc/wireguard/wg0.pub":
                    return pub_file
                if path_str == "/etc/wireguard/wg0.conf":
                    return conf_file
                return real_path(*args)

            MockPath.side_effect = path_factory

            from src.components.wireguard.server import setup
            setup(tmp_path)

        assert conf_file.exists()
        content = conf_file.read_text()
        assert "PrivateKey" in content
        assert "PostUp" in content
        assert "MYPRIVKEY" in content

    def test_skips_conf_if_present(self, tmp_path):
        """wg0.conf présent → fichier non réécrit."""
        wg_dir = tmp_path / "wireguard"
        wg_dir.mkdir()
        key_file = wg_dir / "wg0.key"
        pub_file = wg_dir / "wg0.pub"
        conf_file = wg_dir / "wg0.conf"

        key_file.write_text("MYPRIVKEY\n")
        pub_file.write_text("MYPUBKEY\n")
        original_conf = "[Interface]\nPrivateKey = MYPRIVKEY\nAddress = 10.8.0.1/24\n"
        conf_file.write_text(original_conf)

        def fake_run(cmd, **kwargs):
            return MagicMock(returncode=0, stdout="")

        with patch("src.components.wireguard.server.run", side_effect=fake_run), \
             patch("src.components.wireguard.server._svc"), \
             patch("src.components.wireguard.server.add_wireguard_interface"), \
             patch("src.components.wireguard.server.read_ext_if", return_value="eth0"), \
             patch("src.components.wireguard.server.Path") as MockPath:

            real_path = Path

            def path_factory(*args):
                path_str = str(real_path(*args))
                if path_str == "/etc/wireguard":
                    return wg_dir
                if path_str == "/etc/wireguard/wg0.key":
                    return key_file
                if path_str == "/etc/wireguard/wg0.pub":
                    return pub_file
                if path_str == "/etc/wireguard/wg0.conf":
                    return conf_file
                return real_path(*args)

            MockPath.side_effect = path_factory

            from src.components.wireguard.server import setup
            setup(tmp_path)

        # Content unchanged
        assert conf_file.read_text() == original_conf
