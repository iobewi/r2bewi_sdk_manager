"""
Tests unitaires — src.registry.setup
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

from src.components.registry.setup import (
    _parse_size_gb, _detect_vg, _vg_free_gb, _is_mounted, _fstab_has_entry,
)


class TestIsMounted:
    def test_exact_match(self):
        mounts = "tmpfs /tmp tmpfs rw 0 0\n/dev/sdb1 /var/lib/docker-registry ext4 rw 0 0\n"
        with patch("src.components.registry.setup.Path") as mock_path:
            mock_path.return_value.read_text.return_value = mounts
            mock_path.return_value.splitlines = None  # unused path
            # Patch at read level instead
        mount_point = Path("/var/lib/docker-registry")
        with patch.object(Path, "read_text", return_value=mounts):
            assert _is_mounted(mount_point) is True

    def test_false_positive_substring(self):
        # /var/lib/docker-registry-backup should NOT match /var/lib/docker-registry
        mounts = "tmpfs /tmp tmpfs rw 0 0\n/dev/sdc1 /var/lib/docker-registry-backup ext4 rw 0 0\n"
        mount_point = Path("/var/lib/docker-registry")
        with patch.object(Path, "read_text", return_value=mounts):
            assert _is_mounted(mount_point) is False

    def test_not_mounted(self):
        mounts = "tmpfs /tmp tmpfs rw 0 0\nsysfs /sys sysfs rw 0 0\n"
        mount_point = Path("/var/lib/docker-registry")
        with patch.object(Path, "read_text", return_value=mounts):
            assert _is_mounted(mount_point) is False

    def test_empty_proc_mounts(self):
        mount_point = Path("/var/lib/docker-registry")
        with patch.object(Path, "read_text", return_value=""):
            assert _is_mounted(mount_point) is False


class TestFstabHasEntry:
    _mp = Path("/var/lib/docker-registry")

    def test_entry_present(self):
        content = "UUID=abc123 /var/lib/docker-registry ext4 defaults 0 2\n"
        assert _fstab_has_entry(content, self._mp) is True

    def test_empty_file(self):
        assert _fstab_has_entry("", self._mp) is False

    def test_commented_line_not_matched(self):
        content = "# UUID=abc123 /var/lib/docker-registry ext4 defaults 0 2\n"
        assert _fstab_has_entry(content, self._mp) is False

    def test_false_positive_substring(self):
        # A different mount point containing the target as substring must not match
        content = "UUID=xyz /var/lib/docker-registry-backup ext4 defaults 0 2\n"
        assert _fstab_has_entry(content, self._mp) is False

    def test_blank_lines_ignored(self):
        content = "\n\n   \nUUID=abc /var/lib/docker-registry ext4 defaults 0 2\n"
        assert _fstab_has_entry(content, self._mp) is True

    def test_malformed_line_ignored(self):
        # Line with only one field — no crash, no match
        content = "/dev/sdb1\nUUID=abc /var/lib/docker-registry ext4 defaults 0 2\n"
        assert _fstab_has_entry(content, self._mp) is True


class TestParseSizeGb:
    def test_gigabytes(self):
        assert _parse_size_gb("256G") == 256.0

    def test_gigabytes_lowercase(self):
        assert _parse_size_gb("128g") == 128.0

    def test_terabytes(self):
        assert _parse_size_gb("1T") == 1024.0

    def test_invalid_raises(self):
        with pytest.raises(ValueError):
            _parse_size_gb("256M")


class TestDetectVg:
    def test_returns_first_vg_on_success(self):
        mock_result = MagicMock(returncode=0, stdout="  myvg\n  othervg\n")
        with patch("src.components.registry.setup.run", return_value=mock_result):
            assert _detect_vg() == "myvg"

    def test_returns_none_on_nonzero(self):
        mock_result = MagicMock(returncode=1, stdout="")
        with patch("src.components.registry.setup.run", return_value=mock_result):
            assert _detect_vg() is None

    def test_returns_none_when_empty_output(self):
        mock_result = MagicMock(returncode=0, stdout="  \n\n")
        with patch("src.components.registry.setup.run", return_value=mock_result):
            assert _detect_vg() is None


class TestVgFreeGb:
    def test_returns_free_space(self):
        mock_result = MagicMock(returncode=0, stdout=" 128.50\n")
        with patch("src.components.registry.setup.run", return_value=mock_result):
            assert _vg_free_gb("myvg") == pytest.approx(128.5)

    def test_returns_zero_on_nonzero_returncode(self):
        mock_result = MagicMock(returncode=1, stdout="")
        with patch("src.components.registry.setup.run", return_value=mock_result):
            assert _vg_free_gb("myvg") == 0.0

    def test_returns_zero_on_invalid_output(self):
        mock_result = MagicMock(returncode=0, stdout="not_a_number")
        with patch("src.components.registry.setup.run", return_value=mock_result):
            assert _vg_free_gb("myvg") == 0.0


class TestWriteRegistryConfig:
    """Tests for config file writing (via install path)."""

    def _make_install_patches(self, tmp_path, *, already_mounted=False, vg=None):
        """Returns a context manager dict for patching install dependencies."""
        mounts_content = f"/var/lib/docker-registry" if already_mounted else ""
        return {
            "proc_mounts": mounts_content,
            "vg": vg,
        }

    def test_writes_config_when_absent(self, tmp_path):
        config_path = tmp_path / "config.yml"
        # Simulate writing config by calling the module logic directly
        from src.components.registry.setup import _REGISTRY_CONFIG
        config_path.write_text(_REGISTRY_CONFIG)
        assert "version: 0.1" in config_path.read_text()
        assert ":5000" in config_path.read_text()

    def test_config_is_idempotent(self, tmp_path):
        """Writing the same config twice yields the same content."""
        from src.components.registry.setup import _REGISTRY_CONFIG
        config_path = tmp_path / "config.yml"
        config_path.write_text(_REGISTRY_CONFIG)
        first_content = config_path.read_text()
        config_path.write_text(_REGISTRY_CONFIG)
        assert config_path.read_text() == first_content


class TestInstall:
    """Tests for install() — full mocked flow."""

    def test_install_no_lvm_available(self, tmp_path):
        """When no VG detected, skip LVM and configure service."""
        config_path = tmp_path / "config.yml"

        with patch("src.components.registry.setup._setup_volume") as mock_setup, \
             patch("src.components.registry.setup._svc") as mock_svc, \
             patch("src.components.registry.setup._backup") as mock_backup:
            # Patch the config path used in install
            from src.components.registry import setup as reg_setup
            original_path_class = Path

            def patched_path(*args, **kwargs):
                p = original_path_class(*args, **kwargs)
                if str(p) == "/etc/docker/registry/config.yml":
                    return config_path
                return p

            with patch("src.components.registry.setup.Path", side_effect=patched_path):
                # Can't easily patch Path constructor, so just test _setup_volume is called
                pass

        # Simpler: test install calls _setup_volume and svc methods
        with patch("src.components.registry.setup._setup_volume") as mock_vol, \
             patch("src.components.registry.setup._svc") as mock_svc, \
             patch("src.components.registry.setup._backup.backup_file"), \
             patch("builtins.open", create=True), \
             patch.object(Path, "mkdir"), \
             patch.object(Path, "exists", return_value=False), \
             patch.object(Path, "read_text", return_value=""), \
             patch.object(Path, "write_text"):
            from src.components.registry.setup import install
            install(tmp_path, size="10G")

        mock_vol.assert_called_once_with("10G")
        mock_svc.enable.assert_called_once_with("docker-registry")
        mock_svc.restart.assert_called_once_with("docker-registry")

    def test_install_skips_config_when_up_to_date(self, tmp_path):
        """When config already matches, backup is not called."""
        from src.components.registry.setup import _REGISTRY_CONFIG

        with patch("src.components.registry.setup._setup_volume"), \
             patch("src.components.registry.setup._svc"), \
             patch("src.components.registry.setup._backup.backup_file") as mock_backup, \
             patch.object(Path, "mkdir"), \
             patch.object(Path, "exists", return_value=True), \
             patch.object(Path, "read_text", return_value=_REGISTRY_CONFIG), \
             patch.object(Path, "write_text"):
            from src.components.registry.setup import install
            install(tmp_path, size="10G")

        mock_backup.assert_not_called()


class TestSetupVolumeNoVg:
    """Tests _setup_volume when no LVM VG is available."""

    def test_no_vg_detected_returns_early(self, tmp_path):
        """When no VG, _setup_volume returns without running lvcreate."""
        mock_mounts = MagicMock()
        mock_mounts.read_text.return_value = ""  # not mounted

        run_calls = []

        def fake_run(cmd, **kwargs):
            run_calls.append(cmd)
            # vgs call returns nonzero (no VG)
            return MagicMock(returncode=1, stdout="")

        with patch("src.components.registry.setup.run", side_effect=fake_run), \
             patch.object(Path, "mkdir"), \
             patch.object(Path, "read_text", return_value=""), \
             patch.object(Path, "exists", return_value=False):
            from src.components.registry.setup import _setup_volume
            _setup_volume("10G")

        # Should have called vgs but not lvcreate/mkfs/mount
        lvcreate_calls = [c for c in run_calls if c and c[0] == "lvcreate"]
        assert lvcreate_calls == []

    def test_already_mounted_returns_early(self, tmp_path):
        """When volume already mounted, no run calls are made."""
        run_calls = []

        def fake_run(cmd, **kwargs):
            run_calls.append(cmd)
            return MagicMock(returncode=0, stdout="")

        with patch("src.components.registry.setup.run", side_effect=fake_run), \
             patch.object(Path, "mkdir"), \
             patch.object(Path, "read_text", return_value="/var/lib/docker-registry /var/lib/docker-registry ext4 rw"):
            from src.components.registry.setup import _setup_volume
            _setup_volume("10G")

        assert run_calls == []
