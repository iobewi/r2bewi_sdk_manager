"""
Tests unitaires — src.components.k3s.setup

Couvre :
- deploy : k3s-config.yaml absent → skip
- deploy : registries.yaml absent → skip
- deploy : les deux fichiers présents → écriture dans destinations système
- deploy : contenu identique → idempotent
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


_K3S_CONFIG = "node-label: []\n"
_REGISTRIES = "mirrors: {}\n"

_FILES = {
    "k3s-config.yaml": "/etc/rancher/k3s/config.yaml",
    "registries.yaml": "/etc/rancher/k3s/registries.yaml",
}


def _fake_path_factory(tmp_path: Path):
    """Retourne un constructeur Path qui redirige les chemins /etc/rancher/ vers tmp_path."""
    real_Path = Path

    def fake_path(arg=".", *args):
        p = real_Path(str(arg), *args)
        if str(p) == "/etc/rancher/k3s/config.yaml":
            return tmp_path / "etc" / "rancher" / "k3s" / "config.yaml"
        if str(p) == "/etc/rancher/k3s/registries.yaml":
            return tmp_path / "etc" / "rancher" / "k3s" / "registries.yaml"
        return p

    return fake_path


class TestK3sSetupDeploy:
    def test_missing_source_skips(self, tmp_path):
        """k3s-config.yaml et registries.yaml absents → pas d'écriture."""
        dest_config = tmp_path / "etc" / "rancher" / "k3s" / "config.yaml"
        dest_reg = tmp_path / "etc" / "rancher" / "k3s" / "registries.yaml"

        with patch("src.components.k3s.setup.Path", side_effect=_fake_path_factory(tmp_path)):
            from src.components.k3s.setup import deploy
            deploy(tmp_path)

        assert not dest_config.exists()
        assert not dest_reg.exists()

    def test_deploys_both_files(self, tmp_path):
        """k3s-config.yaml et registries.yaml présents → écrits dans /etc/rancher/k3s/."""
        (tmp_path / "k3s-config.yaml").write_text(_K3S_CONFIG)
        (tmp_path / "registries.yaml").write_text(_REGISTRIES)

        dest_config = tmp_path / "etc" / "rancher" / "k3s" / "config.yaml"
        dest_reg = tmp_path / "etc" / "rancher" / "k3s" / "registries.yaml"

        with patch("src.components.k3s.setup.Path", side_effect=_fake_path_factory(tmp_path)):
            from src.components.k3s.setup import deploy
            deploy(tmp_path)

        assert dest_config.exists()
        assert dest_config.read_text() == _K3S_CONFIG
        assert dest_reg.exists()
        assert dest_reg.read_text() == _REGISTRIES

    def test_deploys_only_present_file(self, tmp_path):
        """Seul k3s-config.yaml présent → registries.yaml non créé."""
        (tmp_path / "k3s-config.yaml").write_text(_K3S_CONFIG)

        dest_config = tmp_path / "etc" / "rancher" / "k3s" / "config.yaml"
        dest_reg = tmp_path / "etc" / "rancher" / "k3s" / "registries.yaml"

        with patch("src.components.k3s.setup.Path", side_effect=_fake_path_factory(tmp_path)):
            from src.components.k3s.setup import deploy
            deploy(tmp_path)

        assert dest_config.exists()
        assert not dest_reg.exists()

    def test_idempotent(self, tmp_path):
        """Contenu identique déjà sur disque → pas de réécriture."""
        (tmp_path / "k3s-config.yaml").write_text(_K3S_CONFIG)
        (tmp_path / "registries.yaml").write_text(_REGISTRIES)

        dest_config = tmp_path / "etc" / "rancher" / "k3s" / "config.yaml"
        dest_reg = tmp_path / "etc" / "rancher" / "k3s" / "registries.yaml"
        dest_config.parent.mkdir(parents=True, exist_ok=True)
        dest_config.write_text(_K3S_CONFIG)
        dest_reg.write_text(_REGISTRIES)

        mtime_config = dest_config.stat().st_mtime
        mtime_reg = dest_reg.stat().st_mtime

        with patch("src.components.k3s.setup.Path", side_effect=_fake_path_factory(tmp_path)):
            from src.components.k3s.setup import deploy
            deploy(tmp_path)

        assert dest_config.stat().st_mtime == mtime_config
        assert dest_reg.stat().st_mtime == mtime_reg
