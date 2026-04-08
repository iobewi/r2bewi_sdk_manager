"""
Tests unitaires — src.components.netplan.setup

Couvre :
- apply : netplan.yaml absent → skip
- apply : déploie netplan.yaml, archive, désactive cloud-init, netplan apply
- apply : k3s déjà installé → netplan apply différé (non appelé)
- apply : contenu identique → idempotent
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest


_NETPLAN_CONF = """\
network:
  version: 2
  ethernets:
    eth0:
      dhcp4: true
"""


def _fake_path_factory(tmp_path: Path):
    """Redirige /etc/netplan/ et /etc/cloud/ vers tmp_path."""
    real_Path = Path

    def fake_path(arg=".", *args):
        p = real_Path(str(arg), *args)
        s = str(p)
        if s == "/etc/netplan/50-r2bewi.yaml":
            return tmp_path / "etc" / "netplan" / "50-r2bewi.yaml"
        if s == "/etc/cloud/cloud.cfg.d":
            return tmp_path / "etc" / "cloud" / "cloud.cfg.d"
        if s.startswith("/etc/cloud/"):
            rel = s[len("/etc/cloud/"):]
            return tmp_path / "etc" / "cloud" / rel
        return p

    return fake_path


class TestNetplanDeploy:
    def test_missing_source_skips(self, tmp_path):
        """netplan.yaml absent → pas d'écriture, pas de run."""
        mock_run = MagicMock()
        with patch("src.components.netplan.setup.run", mock_run), \
             patch("src.components.netplan.setup.Path", side_effect=_fake_path_factory(tmp_path)):
            from src.components.netplan.setup import apply
            apply(tmp_path)
        mock_run.assert_not_called()

    def test_deploys_file_and_applies(self, tmp_path):
        """netplan.yaml présent, k3s absent → écrit et applique netplan."""
        (tmp_path / "netplan.yaml").write_text(_NETPLAN_CONF)
        dest = tmp_path / "etc" / "netplan" / "50-r2bewi.yaml"

        mock_run = MagicMock()
        mock_backup = MagicMock()
        mock_backup.archive_directory.return_value = []

        with patch("src.components.netplan.setup.run", mock_run), \
             patch("src.components.netplan.setup._backup", mock_backup), \
             patch("src.components.netplan.setup.which", return_value=False), \
             patch("src.components.netplan.setup.Path", side_effect=_fake_path_factory(tmp_path)):
            from src.components.netplan.setup import apply
            apply(tmp_path)

        assert dest.exists()
        assert dest.read_text() == _NETPLAN_CONF
        # netplan generate puis apply doivent être appelés
        calls = [c.args[0] for c in mock_run.call_args_list]
        assert ["netplan", "generate"] in calls
        assert ["netplan", "apply"] in calls

    def test_k3s_installed_skips_apply(self, tmp_path):
        """k3s déjà installé → netplan apply NOT appelé (différé au reboot)."""
        (tmp_path / "netplan.yaml").write_text(_NETPLAN_CONF)

        mock_run = MagicMock()
        mock_backup = MagicMock()
        mock_backup.archive_directory.return_value = []

        with patch("src.components.netplan.setup.run", mock_run), \
             patch("src.components.netplan.setup._backup", mock_backup), \
             patch("src.components.netplan.setup.which", return_value=True), \
             patch("src.components.netplan.setup.Path", side_effect=_fake_path_factory(tmp_path)):
            from src.components.netplan.setup import apply
            apply(tmp_path)

        calls = [c.args[0] for c in mock_run.call_args_list]
        assert ["netplan", "generate"] in calls
        assert ["netplan", "apply"] not in calls

    def test_idempotent(self, tmp_path):
        """Contenu identique → pas de réécriture ni de netplan apply."""
        (tmp_path / "netplan.yaml").write_text(_NETPLAN_CONF)
        dest = tmp_path / "etc" / "netplan" / "50-r2bewi.yaml"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(_NETPLAN_CONF)

        mock_run = MagicMock()
        mock_backup = MagicMock()

        mtime_before = dest.stat().st_mtime

        with patch("src.components.netplan.setup.run", mock_run), \
             patch("src.components.netplan.setup._backup", mock_backup), \
             patch("src.components.netplan.setup.Path", side_effect=_fake_path_factory(tmp_path)):
            from src.components.netplan.setup import apply
            apply(tmp_path)

        assert dest.stat().st_mtime == mtime_before
        mock_run.assert_not_called()
        mock_backup.archive_directory.assert_not_called()

    def test_disable_cloud_init_creates_marker(self, tmp_path):
        """_disable_cloud_init_network crée 99-disable-network-config.cfg si cloud.cfg.d existe."""
        cloud_dir = tmp_path / "etc" / "cloud" / "cloud.cfg.d"
        cloud_dir.mkdir(parents=True, exist_ok=True)

        real_Path = Path

        def fake_path(arg=".", *args):
            p = real_Path(str(arg), *args)
            s = str(p)
            if s == "/etc/cloud/cloud.cfg.d":
                return cloud_dir
            if s == "/etc/cloud/cloud.cfg.d/99-disable-network-config.cfg":
                return cloud_dir / "99-disable-network-config.cfg"
            return p

        with patch("src.components.netplan.setup.Path", side_effect=fake_path):
            from src.components.netplan.setup import _disable_cloud_init_network
            _disable_cloud_init_network()

        marker = cloud_dir / "99-disable-network-config.cfg"
        assert marker.exists()
        assert "disabled" in marker.read_text()
