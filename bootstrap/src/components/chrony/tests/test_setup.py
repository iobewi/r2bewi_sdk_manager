"""
Tests unitaires — src.components.chrony.setup

Couvre :
- apply : absence de chrony.conf → skip
- apply : déploiement de chrony.conf vers destination système
- apply : contenu identique → idempotent (pas de réécriture)
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


_CHRONY_CONF = """\
# NTP pools
pool 2.debian.pool.ntp.org iburst
"""


class TestChronyDeploy:
    def test_no_chrony_conf_skips(self, tmp_path):
        """Pas de chrony.conf dans node_dir → rien n'est écrit."""
        mock_svc = MagicMock()
        with patch("src.components.chrony.setup._svc", mock_svc):
            from src.components.chrony.setup import apply
            apply(tmp_path)

        mock_svc.enable.assert_not_called()
        mock_svc.restart.assert_not_called()

    def test_deploys_chrony_conf(self, tmp_path):
        """chrony.conf présent → écrit dans la destination système + active le service."""
        (tmp_path / "chrony.conf").write_text(_CHRONY_CONF)

        # Destination simulée dans tmp_path
        dest = tmp_path / "etc" / "chrony" / "chrony.conf"

        mock_svc = MagicMock()

        # Remplace Path("/etc/chrony/chrony.conf") par notre dest dans tmp_path
        original_path_call = Path.__new__

        # Approche : on remplace directement la constante dest dans apply()
        # en patchant Path() pour les chemins système
        real_Path = Path

        def fake_path(arg=".", *args):
            p = real_Path(str(arg), *args)
            if str(p) == "/etc/chrony/chrony.conf":
                return dest
            return p

        with patch("src.components.chrony.setup._svc", mock_svc), \
             patch("src.components.chrony.setup.Path", side_effect=fake_path):
            from src.components.chrony.setup import apply
            apply(tmp_path)

        assert dest.exists()
        assert dest.read_text() == _CHRONY_CONF
        mock_svc.enable.assert_called_once_with("chrony")
        mock_svc.restart.assert_called_once_with("chrony")

    def test_idempotent_same_content(self, tmp_path):
        """Contenu identique déjà sur disque → pas de réécriture ni restart."""
        (tmp_path / "chrony.conf").write_text(_CHRONY_CONF)

        # Destination avec contenu identique déjà présent
        dest = tmp_path / "etc" / "chrony" / "chrony.conf"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(_CHRONY_CONF)

        mock_svc = MagicMock()
        real_Path = Path

        def fake_path(arg=".", *args):
            p = real_Path(str(arg), *args)
            if str(p) == "/etc/chrony/chrony.conf":
                return dest
            return p

        with patch("src.components.chrony.setup._svc", mock_svc), \
             patch("src.components.chrony.setup.Path", side_effect=fake_path):
            from src.components.chrony.setup import apply
            # Sauvegarde mtime pour vérifier qu'il n'y a pas eu écriture
            mtime_before = dest.stat().st_mtime
            apply(tmp_path)
            mtime_after = dest.stat().st_mtime

        assert mtime_before == mtime_after
        mock_svc.enable.assert_not_called()
        mock_svc.restart.assert_not_called()
