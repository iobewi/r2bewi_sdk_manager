"""
Tests unitaires — src.core.status

Couvre :
- _read_bridge_name : lecture bridge depuis dnsmasq.conf
- _row : affichage icônes ✓ ✗ ?
- _status_server : exécution complète mockée
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


class TestStatusHelpers:
    def test_read_bridge_name_from_dnsmasq(self, tmp_path):
        """Lit l'interface bridge depuis dnsmasq.conf."""
        (tmp_path / "dnsmasq.conf").write_text(
            "interface=br-lan\nbind-interfaces\ndomain=local\n"
        )
        from src.core.status import _read_bridge_name
        assert _read_bridge_name(tmp_path) == "br-lan"

    def test_read_bridge_name_default(self, tmp_path):
        """Fichier absent → retourne 'br0'."""
        from src.core.status import _read_bridge_name
        assert _read_bridge_name(tmp_path) == "br0"

    def test_read_bridge_name_no_interface_line(self, tmp_path):
        """dnsmasq.conf sans ligne interface= → retourne 'br0'."""
        (tmp_path / "dnsmasq.conf").write_text("bind-interfaces\n")
        from src.core.status import _read_bridge_name
        assert _read_bridge_name(tmp_path) == "br0"

    def test_row_ok(self, capsys):
        """_row avec ok=True affiche ✓."""
        from src.core.status import _row
        _row("label", "value", ok=True)
        captured = capsys.readouterr()
        assert "✓" in captured.out
        assert "label" in captured.out
        assert "value" in captured.out

    def test_row_fail(self, capsys):
        """_row avec ok=False affiche ✗."""
        from src.core.status import _row
        _row("label", "value", ok=False)
        captured = capsys.readouterr()
        assert "✗" in captured.out

    def test_row_unknown(self, capsys):
        """_row avec ok=None affiche ?."""
        from src.core.status import _row
        _row("label", "value", ok=None)
        captured = capsys.readouterr()
        assert "?" in captured.out


class TestStatusServer:
    def test_status_server_runs(self, tmp_path, capsys):
        """_status_server s'exécute sans erreur avec tout mocké."""
        # Prépare un node dir minimal
        (tmp_path / "dnsmasq.conf").write_text("interface=br0\n")

        mock_bridge_address = MagicMock(return_value="192.168.1.1/24")
        mock_sysctl_get = MagicMock(return_value="1")
        mock_service_active = MagicMock(return_value=True)
        mock_k3s_installed = MagicMock(return_value=True)
        mock_k3s_token_present = MagicMock(return_value=True)
        mock_node_ready = MagicMock(return_value=(True, "r2bewi Ready 2d"))
        mock_ssh_key_present = MagicMock(return_value=True)
        mock_file_present = MagicMock(return_value=True)
        mock_list_backups = MagicMock(return_value={})
        mock_all_managed_paths = MagicMock(return_value=frozenset(["/etc/netplan/50-r2bewi.yaml"]))

        with patch("src.core.status._state") as mock_state, \
             patch("src.core.status._backup") as mock_backup, \
             patch("src.core.status.all_managed_paths", mock_all_managed_paths):
            mock_state.bridge_address = mock_bridge_address
            mock_state.sysctl_get = mock_sysctl_get
            mock_state.service_active = mock_service_active
            mock_state.k3s_installed = mock_k3s_installed
            mock_state.k3s_token_present = mock_k3s_token_present
            mock_state.node_ready = mock_node_ready
            mock_state.ssh_key_present = mock_ssh_key_present
            mock_state.file_present = mock_file_present
            mock_backup.list_backups = mock_list_backups
            mock_backup.BACKUP_ROOT = Path("/var/lib/r2bewi/backup")

            from src.core.status import _status_server
            _status_server("r2bewi", tmp_path)

        captured = capsys.readouterr()
        assert "Réseau" in captured.out
        assert "K3s server" in captured.out
        assert "SSH" in captured.out

    def test_status_server_k3s_not_installed(self, tmp_path, capsys):
        """_status_server avec k3s non installé — pas d'appel node_ready."""
        (tmp_path / "dnsmasq.conf").write_text("interface=br0\n")

        with patch("src.core.status._state") as mock_state, \
             patch("src.core.status._backup") as mock_backup, \
             patch("src.core.status.all_managed_paths", return_value=frozenset()):
            mock_state.bridge_address = MagicMock(return_value=None)
            mock_state.sysctl_get = MagicMock(return_value=None)
            mock_state.service_active = MagicMock(return_value=False)
            mock_state.k3s_installed = MagicMock(return_value=False)
            mock_state.k3s_token_present = MagicMock(return_value=False)
            mock_state.node_ready = MagicMock()
            mock_state.ssh_key_present = MagicMock(return_value=False)
            mock_state.file_present = MagicMock(return_value=False)
            mock_backup.list_backups = MagicMock(return_value={})
            mock_backup.BACKUP_ROOT = Path("/var/lib/r2bewi/backup")

            from src.core.status import _status_server
            _status_server("r2bewi", tmp_path)

        # node_ready ne doit pas être appelé si k3s non installé
        mock_state.node_ready.assert_not_called()


class TestStatusBackups:
    def test_status_backups_empty(self, capsys):
        """Aucune sauvegarde → affiche message aucune."""
        with patch("src.core.status._backup") as mock_backup:
            mock_backup.list_backups = MagicMock(return_value={})
            mock_backup.BACKUP_ROOT = Path("/var/lib/r2bewi/backup")
            from src.core.status import _status_backups
            _status_backups()
        captured = capsys.readouterr()
        assert "aucune sauvegarde" in captured.out

    def test_status_backups_with_data(self, capsys):
        """Sauvegardes présentes → affiche le comptage."""
        with patch("src.core.status._backup") as mock_backup:
            mock_backup.list_backups = MagicMock(
                return_value={"file1": ["v1", "v2"], "file2": ["v1"]}
            )
            mock_backup.BACKUP_ROOT = Path("/var/lib/r2bewi/backup")
            from src.core.status import _status_backups
            _status_backups()
        captured = capsys.readouterr()
        assert "2 fichier(s)" in captured.out
        assert "3 version(s)" in captured.out
