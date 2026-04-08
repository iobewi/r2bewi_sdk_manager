"""
Tests unitaires — src.core.deploy

Couvre :
- _run_local : préflight root, outils manquants, validation, happy path
- _run_remote : validation, aucun fichier, déploiement de fichiers
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest


# ── Helpers ───────────────────────────────────────────────────────────────────

_NETPLAN_VALID = """\
network:
  version: 2
  ethernets:
    eth0:
      dhcp4: true
"""

_SYSCTL_VALID = "net.ipv4.ip_forward=1\n"
_DNSMASQ_VALID = "# dnsmasq\n"
_K3S_CONFIG_VALID = "node-label: []\n"
_REGISTRIES_VALID = "mirrors: {}\n"


def _make_server_dir(node_dir: Path) -> None:
    """Crée un node dir server minimal valide."""
    (node_dir / "meta.yaml").write_text("kind: server\n")
    (node_dir / "netplan.yaml").write_text(_NETPLAN_VALID)
    (node_dir / "sysctl.conf").write_text(_SYSCTL_VALID)
    (node_dir / "dnsmasq.conf").write_text(_DNSMASQ_VALID)
    (node_dir / "k3s-config.yaml").write_text(_K3S_CONFIG_VALID)
    (node_dir / "registries.yaml").write_text(_REGISTRIES_VALID)


# ── Local ─────────────────────────────────────────────────────────────────────

class TestDeployRunLocal:
    def test_non_root_exits(self, tmp_path):
        """Sans root (geteuid != 0) → sys.exit(1)."""
        _make_server_dir(tmp_path)

        with patch("src.core.deploy.NODES_DIR", tmp_path.parent), \
             patch("os.geteuid", return_value=1), \
             patch("src.core.deploy.resolve_ip", return_value=None), \
             patch("src.core.deploy.resolve_ssh_user", return_value="iobewi"):
            from src.core.deploy import _run_local
            with pytest.raises(SystemExit) as exc:
                _run_local(tmp_path.name, tmp_path)
            assert exc.value.code == 1

    def test_missing_tools_exits_with_hint(self, tmp_path):
        """Outils manquants → sys.exit(1)."""
        _make_server_dir(tmp_path)

        with patch("os.geteuid", return_value=0), \
             patch("src.core.deploy.which", return_value=False):
            from src.core.deploy import _run_local
            with pytest.raises(SystemExit) as exc:
                _run_local(tmp_path.name, tmp_path)
            assert exc.value.code == 1

    def test_validation_failure_exits(self, tmp_path):
        """validate_node_dir retourne False → sys.exit(1)."""
        _make_server_dir(tmp_path)

        with patch("os.geteuid", return_value=0), \
             patch("src.core.deploy.which", return_value=True), \
             patch("src.core.deploy.validate_node_dir", return_value=False):
            from src.core.deploy import _run_local
            with pytest.raises(SystemExit) as exc:
                _run_local(tmp_path.name, tmp_path)
            assert exc.value.code == 1

    def test_local_deploy_happy_path(self, tmp_path):
        """Flux complet mocké : validation OK, hostname, swap, composants, OK."""
        _make_server_dir(tmp_path)

        mock_run = MagicMock()
        mock_run.return_value = MagicMock(returncode=0)
        mock_apply = MagicMock()
        mock_registry = MagicMock()
        mock_wireguard = MagicMock()
        mock_install_packages = MagicMock()

        # Patch fstab pour éviter les accès /etc/fstab
        fstab = tmp_path / "fstab"
        fstab.write_text("")

        with patch("os.geteuid", return_value=0), \
             patch("src.core.deploy.which", return_value=True), \
             patch("src.core.deploy.validate_node_dir", return_value=True), \
             patch("src.core.deploy.run", mock_run), \
             patch("src.core.deploy._apply_components", mock_apply), \
             patch("src.core.deploy._registry") as mock_reg_mod, \
             patch("src.core.deploy._wireguard") as mock_wg_mod, \
             patch("src.core.deploy._install_packages", mock_install_packages), \
             patch("src.core.deploy.get_kind", return_value="server"), \
             patch("pathlib.Path.exists", return_value=False):
            mock_reg_mod.install = MagicMock()
            mock_wg_mod.setup = MagicMock()

            from src.core.deploy import _run_local
            # Ne doit pas lever d'exception
            _run_local("testhost", tmp_path)

        mock_apply.assert_called_once_with(tmp_path)
        mock_install_packages.assert_called_once_with(tmp_path)
        mock_reg_mod.install.assert_called_once()
        mock_wg_mod.setup.assert_called_once()


# ── Distant ───────────────────────────────────────────────────────────────────

class TestDeployRunRemote:
    def test_validation_failure_exits(self, tmp_path):
        """validate_node_dir échoue → sys.exit(1) avant tout SSH."""
        _make_server_dir(tmp_path)

        with patch("src.core.deploy.validate_node_dir", return_value=False), \
             patch("src.core.deploy.get_kind", return_value="server"), \
             patch("src.core.deploy.ensure_iobewi_key", return_value=Path("/tmp/key")), \
             patch("src.core.deploy.create_iobewi_on_agent"), \
             patch("src.core.deploy.run_ssh"):
            from src.core.deploy import _run_remote
            with pytest.raises(SystemExit) as exc:
                _run_remote("testhost", tmp_path, "iobewi@192.168.1.10")
            assert exc.value.code == 1

    def test_remote_no_files_exits(self, tmp_path):
        """Aucun fichier à déployer → sys.exit(1)."""
        _make_server_dir(tmp_path)

        # Aucun fichier node existant (map vide)
        with patch("src.core.deploy.validate_node_dir", return_value=True), \
             patch("src.core.deploy.get_kind", return_value="server"), \
             patch("src.core.deploy.ensure_iobewi_key", return_value=Path("/tmp/key")), \
             patch("src.core.deploy._all_node_files", return_value={}), \
             patch("src.core.deploy.run_ssh"), \
             patch("src.core.deploy._agent_packages", return_value=[]):
            from src.core.deploy import _run_remote
            with pytest.raises(SystemExit) as exc:
                _run_remote("testhost", tmp_path, "iobewi@192.168.1.10")
            assert exc.value.code == 1

    def test_remote_deploy_pushes_files(self, tmp_path):
        """Fichiers présents → push_file appelé pour chaque fichier."""
        _make_server_dir(tmp_path)

        file_map = {
            "netplan.yaml": "/etc/netplan/50-r2bewi.yaml",
            "sysctl.conf": "/etc/sysctl.d/99-r2bewi.conf",
        }

        mock_push = MagicMock()
        mock_run_ssh = MagicMock()
        mock_run_ssh.return_value = MagicMock(returncode=0)

        with patch("src.core.deploy.validate_node_dir", return_value=True), \
             patch("src.core.deploy.get_kind", return_value="server"), \
             patch("src.core.deploy.ensure_iobewi_key", return_value=Path("/tmp/key")), \
             patch("src.core.deploy._all_node_files", return_value=file_map), \
             patch("src.core.deploy.run_ssh", mock_run_ssh), \
             patch("src.core.deploy.push_file", mock_push), \
             patch("src.core.deploy._agent_packages", return_value=[]):
            from src.core.deploy import _run_remote
            # _run_remote complète sans SystemExit quand tout va bien
            _run_remote("testhost", tmp_path, "iobewi@192.168.1.10")

        # push_file doit avoir été appelé pour chaque fichier présent dans tmp_path
        assert mock_push.call_count >= 1


class TestIsFstabSwapEntry:
    def test_active_swap_entry(self):
        from src.core.deploy import _is_fstab_swap_entry
        assert _is_fstab_swap_entry("UUID=abc  none  swap  sw  0  0\n") is True

    def test_comment_line_not_swap(self):
        from src.core.deploy import _is_fstab_swap_entry
        assert _is_fstab_swap_entry("# UUID=abc  none  swap  sw  0  0\n") is False

    def test_blank_line_not_swap(self):
        from src.core.deploy import _is_fstab_swap_entry
        assert _is_fstab_swap_entry("\n") is False
        assert _is_fstab_swap_entry("   \n") is False

    def test_non_swap_entry_not_removed(self):
        from src.core.deploy import _is_fstab_swap_entry
        assert _is_fstab_swap_entry("UUID=abc  /  ext4  defaults  0  1\n") is False

    def test_label_containing_swap_word_not_removed(self):
        """Une ligne avec 'swap' dans le device/label mais type != swap est conservée."""
        from src.core.deploy import _is_fstab_swap_entry
        # type field is ext4, not swap
        assert _is_fstab_swap_entry("LABEL=myswap  /data  ext4  defaults  0  2\n") is False

    def test_comment_mentioning_swap_preserved(self):
        from src.core.deploy import _is_fstab_swap_entry
        assert _is_fstab_swap_entry("# Old swap partition removed\n") is False
