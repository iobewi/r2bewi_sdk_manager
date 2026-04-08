"""
Tests unitaires — src.components.sysctl.setup

Couvre :
- apply : sysctl.conf absent → skip
- apply : déploie sysctl.conf et lance sysctl --system
- apply : contenu identique → idempotent
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


_SYSCTL_CONF = "net.ipv4.ip_forward=1\nnet.bridge.bridge-nf-call-iptables=1\n"


class TestSysctlDeploy:
    def test_missing_source_skips(self, tmp_path):
        """sysctl.conf absent dans node_dir → pas d'écriture, pas d'erreur."""
        mock_run = MagicMock()
        with patch("src.components.sysctl.setup.run", mock_run):
            from src.components.sysctl.setup import apply
            apply(tmp_path)
        mock_run.assert_not_called()

    def test_deploys_file(self, tmp_path):
        """sysctl.conf présent → écrit vers destination système et lance sysctl --system."""
        (tmp_path / "sysctl.conf").write_text(_SYSCTL_CONF)
        dest = tmp_path / "etc" / "sysctl.d" / "99-r2bewi.conf"

        mock_run = MagicMock()
        real_Path = Path

        def fake_path(arg=".", *args):
            p = real_Path(str(arg), *args)
            if str(p) == "/etc/sysctl.d/99-r2bewi.conf":
                return dest
            return p

        with patch("src.components.sysctl.setup.run", mock_run), \
             patch("src.components.sysctl.setup.Path", side_effect=fake_path):
            from src.components.sysctl.setup import apply
            apply(tmp_path)

        assert dest.exists()
        assert dest.read_text() == _SYSCTL_CONF
        mock_run.assert_called_once_with(["sysctl", "--system"])

    def test_idempotent(self, tmp_path):
        """Contenu identique déjà sur disque → pas de réécriture, pas de sysctl --system."""
        (tmp_path / "sysctl.conf").write_text(_SYSCTL_CONF)
        dest = tmp_path / "etc" / "sysctl.d" / "99-r2bewi.conf"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(_SYSCTL_CONF)

        mock_run = MagicMock()
        real_Path = Path

        def fake_path(arg=".", *args):
            p = real_Path(str(arg), *args)
            if str(p) == "/etc/sysctl.d/99-r2bewi.conf":
                return dest
            return p

        mtime_before = dest.stat().st_mtime

        with patch("src.components.sysctl.setup.run", mock_run), \
             patch("src.components.sysctl.setup.Path", side_effect=fake_path):
            from src.components.sysctl.setup import apply
            apply(tmp_path)

        assert dest.stat().st_mtime == mtime_before
        mock_run.assert_not_called()
