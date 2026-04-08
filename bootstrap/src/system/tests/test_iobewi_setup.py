"""
Tests unitaires — src.system.iobewi_setup

Couvre :
- create_iobewi_on_agent : pub_key_content transporté via base64 interne
  (anti-régression : un commentaire de clé SSH contenant une apostrophe
   ne doit pas interrompre le script shell exécuté sur l'agent)
"""
from __future__ import annotations

import base64
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.system.iobewi_setup import create_iobewi_on_agent


def _make_key_files(tmp_path: Path, pub_key_content: str) -> Path:
    """Crée une paire de fichiers clé factices et retourne le chemin de la clé privée."""
    key = tmp_path / "id_ed25519"
    key.write_text("PRIVATE_KEY")
    (tmp_path / "id_ed25519.pub").write_text(pub_key_content)
    return key


class TestCreateIobewi:
    """Vérifie que la clé publique est transportée via base64, sans interpolation shell directe."""

    def _run_and_capture_script(self, pub_key_content: str, tmp_path: Path) -> str:
        """
        Lance create_iobewi_on_agent avec la clé factice et retourne le script
        envoyé à l'agent (décodé depuis le base64 de transport).
        """
        key = _make_key_files(tmp_path, pub_key_content)
        captured_scripts: list[str] = []

        def fake_run_ssh(target, remote_cmd, **kwargs):
            # Capture la commande SSH distante
            captured_scripts.append(remote_cmd)
            return MagicMock(returncode=1)  # returncode=1 → pas idempotent → exécute le script

        with patch("src.system.iobewi_setup.run_ssh", side_effect=fake_run_ssh):
            create_iobewi_on_agent("ubuntu@192.168.82.101", key)

        # La dernière commande est du type : echo <BASE64> | base64 -d | sudo bash
        # shlex.quote() ne quote pas les chaînes base64 (alphanumériques + +/=, tous sûrs)
        assert captured_scripts, "Aucune commande SSH émise"
        last = captured_scripts[-1]
        import re
        m = re.search(r"echo\s+'?([A-Za-z0-9+/=]+)'?", last)
        assert m, f"Payload base64 non trouvé dans : {last!r}"
        return base64.b64decode(m.group(1)).decode()

    def test_pub_key_not_interpolated_directly(self, tmp_path):
        """La clé publique brute ne doit pas apparaître directement dans le script envoyé."""
        pub_key = "ssh-ed25519 AAAA... iobewi@r2bewi"
        script = self._run_and_capture_script(pub_key, tmp_path)
        assert pub_key not in script, (
            "La clé publique brute est interpolée directement dans le script — risque de shell injection"
        )

    def test_pub_key_transported_via_base64(self, tmp_path):
        """La clé doit être encodée en base64 dans le script."""
        pub_key = "ssh-ed25519 AAAA... iobewi@r2bewi"
        pub_key_b64 = base64.b64encode(pub_key.encode()).decode()
        script = self._run_and_capture_script(pub_key, tmp_path)
        assert pub_key_b64 in script, "L'encodage base64 de la clé doit être présent dans le script"

    def test_key_with_apostrophe_in_comment_does_not_break(self, tmp_path):
        """Un commentaire de clé avec apostrophe ne doit pas interrompre le script shell."""
        pub_key = "ssh-ed25519 AAAA... it's a valid comment"
        script = self._run_and_capture_script(pub_key, tmp_path)
        # Le script doit contenir une variable PUB_KEY décodée, pas la clé brute
        assert "PUB_KEY=" in script
        assert "it's" not in script

    def test_script_uses_pub_key_variable(self, tmp_path):
        """Le script doit utiliser $PUB_KEY pour grep et tee, pas une valeur littérale."""
        pub_key = "ssh-ed25519 AAAA... iobewi@r2bewi"
        script = self._run_and_capture_script(pub_key, tmp_path)
        assert '"$PUB_KEY"' in script or "$PUB_KEY" in script, (
            "Le script doit référencer $PUB_KEY pour grep et tee"
        )
