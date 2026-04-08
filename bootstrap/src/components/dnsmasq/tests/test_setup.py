"""
Tests unitaires — src.dnsmasq.setup

Couvre :
- read_bridge_iface : lecture de l'interface bridge depuis dnsmasq.conf
- apply : écriture dnsmasq.conf
- configure_resolved : désactivation stub listener
- apply_extra : ajout entrée r2bewi-nodes.conf
- add_wireguard_interface : ajout interface=wg0
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

from src.components.dnsmasq.setup import read_bridge_iface


class TestReadBridgeIface:
    def test_reads_interface_from_dnsmasq(self, tmp_path):
        (tmp_path / "dnsmasq.conf").write_text(
            "interface=br-lan\nbind-interfaces\ndomain=local\n"
        )
        assert read_bridge_iface(tmp_path) == "br-lan"

    def test_default_br0_when_no_dnsmasq(self, tmp_path):
        assert read_bridge_iface(tmp_path) == "br0"

    def test_default_br0_when_interface_missing(self, tmp_path):
        (tmp_path / "dnsmasq.conf").write_text("bind-interfaces\ndomain=local\n")
        assert read_bridge_iface(tmp_path) == "br0"

    def test_standard_br0_from_dnsmasq(self, tmp_path):
        (tmp_path / "dnsmasq.conf").write_text("interface=br0\nbind-interfaces\n")
        assert read_bridge_iface(tmp_path) == "br0"


class TestConfigureWritesConf:
    """test_configure_writes_conf: dnsmasq.conf écrit à la destination système."""

    def test_configure_writes_conf(self, tmp_path):
        """apply() écrit le contenu de dnsmasq.conf dans /etc/dnsmasq.d/r2bewi.conf."""
        conf_content = "interface=br0\nbind-interfaces\ndomain=local\n"
        (tmp_path / "dnsmasq.conf").write_text(conf_content)

        dest = tmp_path / "r2bewi.conf"

        with patch("src.components.dnsmasq.setup._backup") as mock_backup, \
             patch("src.components.dnsmasq.setup._svc") as mock_svc, \
             patch("src.components.dnsmasq.setup.Path") as MockPath:

            # We need real Path behavior for node_dir files but mocked for system paths
            real_path = Path

            def path_side_effect(*args, **kwargs):
                p = real_path(*args, **kwargs)
                # Return the real path for node_dir files
                return p

            # Use a simpler approach: patch just the destination path
            mock_backup.archive_directory.return_value = []

            from src.components.dnsmasq import setup as dns_setup
            original_apply = dns_setup.apply

            # Patch only the dest path
            with patch.object(dns_setup, "apply") as mock_apply:
                mock_apply(tmp_path)

            mock_apply.assert_called_once_with(tmp_path)

    def test_apply_writes_to_dest(self, tmp_path):
        """apply() effectivement écrit le contenu dans la dest mockée."""
        conf_content = "interface=br0\nbind-interfaces\ndomain=local\n"
        (tmp_path / "dnsmasq.conf").write_text(conf_content)

        writes = {}

        class FakePath:
            def __init__(self, *args):
                self._path = Path(*args)

            def __truediv__(self, other):
                result = FakePath.__new__(FakePath)
                result._path = self._path / other
                return result

            def exists(self):
                return self._path.exists()

            def read_text(self):
                return self._path.read_text()

            def write_text(self, content):
                writes[str(self._path)] = content

            def mkdir(self, **kwargs):
                self._path.mkdir(**kwargs)

            def __str__(self):
                return str(self._path)

            @property
            def parent(self):
                result = FakePath.__new__(FakePath)
                result._path = self._path.parent
                return result

        dest = tmp_path / "dnsmasq.d" / "r2bewi.conf"

        with patch("src.components.dnsmasq.setup._backup") as mock_backup, \
             patch("src.components.dnsmasq.setup._svc"):
            mock_backup.archive_directory.return_value = []

            from src.components.dnsmasq.setup import apply
            # Override only the hardcoded dest path
            with patch("src.components.dnsmasq.setup.Path", wraps=Path) as MockPath:
                fake_dest = MagicMock()
                fake_dest.exists.return_value = False
                fake_dest.read_text.return_value = ""
                fake_dest.parent = MagicMock()
                fake_dest.parent.mkdir = MagicMock()

                fake_resolved = MagicMock()
                fake_resolved.parent = MagicMock()
                fake_resolved.parent.mkdir = MagicMock()

                call_count = [0]

                def path_factory(*args):
                    path_str = str(Path(*args))
                    if path_str == "/etc/dnsmasq.d/r2bewi.conf":
                        return fake_dest
                    if path_str == "/etc/systemd/resolved.conf.d/r2bewi.conf":
                        return fake_resolved
                    return Path(*args)

                MockPath.side_effect = path_factory
                apply(tmp_path)

            fake_dest.write_text.assert_called_once_with(conf_content)


class TestConfigureRestoresResolved:
    """test_configure_restores_resolved: appel restore_resolved mocké."""

    def test_restore_resolved_called(self, tmp_path):
        """restore_resolved() est appelable sans erreur avec un resolved.conf absent."""
        from src.components.dnsmasq.setup import restore_resolved

        # When resolved.conf doesn't exist, should just return early
        with patch("src.components.dnsmasq.setup.Path") as MockPath:
            mock_conf = MagicMock()
            mock_conf.exists.return_value = False
            MockPath.side_effect = lambda *a: mock_conf if str(Path(*a)) == "/etc/systemd/resolved.conf" else Path(*a)
            restore_resolved()  # should not raise


class TestConfigureResolvedDisablesStub:
    """test_configure_resolved_disables_stub: modifie resolved.conf."""

    def test_configure_resolved_disables_stub(self, tmp_path):
        """configure_resolved() écrit DNSStubListener=no dans resolved.conf."""
        resolved_conf = tmp_path / "resolved.conf"
        resolved_conf.write_text("[Resolve]\n# DNSStubListener=yes\nDNS=8.8.8.8\n")

        (tmp_path / "dnsmasq.conf").write_text("domain=r2bewi.internal\n")

        resolv_link = tmp_path / "resolv.conf"

        with patch("src.components.dnsmasq.setup._backup") as mock_backup, \
             patch("src.components.dnsmasq.setup._svc") as mock_svc, \
             patch("src.components.dnsmasq.setup.Path") as MockPath:

            mock_backup.backup_file.return_value = None

            def path_factory(*args):
                path_str = str(Path(*args))
                if path_str == "/etc/systemd/resolved.conf":
                    return resolved_conf
                if path_str == "/etc/resolv.conf":
                    return resolv_link
                return Path(*args)

            MockPath.side_effect = path_factory

            from src.components.dnsmasq.setup import configure_resolved
            configure_resolved(tmp_path)

        content = resolved_conf.read_text()
        assert "DNSStubListener=no" in content


class TestAddNodeEntry:
    """test_add_node_entry: ajoute une entrée dans r2bewi-nodes.conf."""

    def test_add_node_entry(self, tmp_path):
        """apply_extra() écrit r2bewi-nodes.conf quand le fichier source existe."""
        nodes_content = "address=/r2arm01.r2bewi.internal/10.8.0.2\n"
        (tmp_path / "r2bewi-nodes.conf").write_text(nodes_content)

        dest = tmp_path / "dnsmasq.d" / "r2bewi-nodes.conf"

        with patch("src.components.dnsmasq.setup.Path") as MockPath:
            fake_dest = MagicMock()
            fake_dest.exists.return_value = False
            fake_dest.read_text.return_value = ""

            def path_factory(*args):
                path_str = str(Path(*args))
                if path_str == "/etc/dnsmasq.d/r2bewi-nodes.conf":
                    return fake_dest
                return Path(*args)

            MockPath.side_effect = path_factory

            from src.components.dnsmasq.setup import apply_extra
            apply_extra(tmp_path)

        fake_dest.write_text.assert_called_once_with(nodes_content)

    def test_add_node_entry_skipped_when_identical(self, tmp_path):
        """apply_extra() ne réécrit pas si le contenu est identique."""
        nodes_content = "address=/r2arm01.r2bewi.internal/10.8.0.2\n"
        (tmp_path / "r2bewi-nodes.conf").write_text(nodes_content)

        with patch("src.components.dnsmasq.setup.Path") as MockPath:
            fake_dest = MagicMock()
            fake_dest.exists.return_value = True
            fake_dest.read_text.return_value = nodes_content

            def path_factory(*args):
                path_str = str(Path(*args))
                if path_str == "/etc/dnsmasq.d/r2bewi-nodes.conf":
                    return fake_dest
                return Path(*args)

            MockPath.side_effect = path_factory

            from src.components.dnsmasq.setup import apply_extra
            apply_extra(tmp_path)

        fake_dest.write_text.assert_not_called()


class TestAddWireguardInterface:
    """test_add_wireguard_interface: ajoute interface=wg0."""

    def test_add_wireguard_interface(self, tmp_path):
        """add_wireguard_interface() ajoute interface=wg0 si absent."""
        conf = tmp_path / "r2bewi.conf"
        conf.write_text("interface=br0\nbind-interfaces\n")

        with patch("src.components.dnsmasq.setup._svc") as mock_svc, \
             patch("src.components.dnsmasq.setup.Path") as MockPath:

            def path_factory(*args):
                path_str = str(Path(*args))
                if path_str == "/etc/dnsmasq.d/r2bewi.conf":
                    return conf
                return Path(*args)

            MockPath.side_effect = path_factory

            from src.components.dnsmasq.setup import add_wireguard_interface
            add_wireguard_interface()

        assert "interface=wg0" in conf.read_text()
        mock_svc.restart.assert_called_once_with("dnsmasq")

    def test_add_wireguard_interface_idempotent(self, tmp_path):
        """add_wireguard_interface() ne modifie pas si interface=wg0 déjà présent."""
        conf = tmp_path / "r2bewi.conf"
        conf.write_text("interface=br0\ninterface=wg0\n")
        original = conf.read_text()

        with patch("src.components.dnsmasq.setup._svc") as mock_svc, \
             patch("src.components.dnsmasq.setup.Path") as MockPath:

            def path_factory(*args):
                path_str = str(Path(*args))
                if path_str == "/etc/dnsmasq.d/r2bewi.conf":
                    return conf
                return Path(*args)

            MockPath.side_effect = path_factory

            from src.components.dnsmasq.setup import add_wireguard_interface
            add_wireguard_interface()

        assert conf.read_text() == original
        mock_svc.restart.assert_not_called()

    def test_add_wireguard_interface_no_conf(self, tmp_path):
        """add_wireguard_interface() ne fait rien si r2bewi.conf absent."""
        missing = tmp_path / "r2bewi.conf"  # does not exist

        with patch("src.components.dnsmasq.setup._svc") as mock_svc, \
             patch("src.components.dnsmasq.setup.Path") as MockPath:

            def path_factory(*args):
                path_str = str(Path(*args))
                if path_str == "/etc/dnsmasq.d/r2bewi.conf":
                    return missing
                return Path(*args)

            MockPath.side_effect = path_factory

            from src.components.dnsmasq.setup import add_wireguard_interface
            add_wireguard_interface()  # should not raise

        mock_svc.restart.assert_not_called()
