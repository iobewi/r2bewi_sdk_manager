"""Tests pour validate_node_dir() — fichiers requis et validation de contenu."""
from __future__ import annotations

import pytest
from pathlib import Path
from unittest.mock import patch


# Contenu YAML minimal valide pour chaque fichier requis
_NETPLAN_VALID = """\
network:
  version: 2
  ethernets:
    eth0:
      dhcp4: true
"""

_SYSCTL_VALID = """\
# sysctl config
net.ipv4.ip_forward=1
"""

_DNSMASQ_VALID = """\
# dnsmasq config
"""

_K3S_CONFIG_SERVER_VALID = """\
node-label: []
"""

_K3S_CONFIG_AGENT_VALID = """\
server: https://192.168.1.1:6443
token: mytoken
node-label: []
"""

_REGISTRIES_VALID = """\
mirrors: {}
"""

_NODE_PROFILE_VALID = """\
labels:
  env: test
"""


def _write_server_files(node_dir: Path, k3s_content: str = _K3S_CONFIG_SERVER_VALID) -> None:
    """Écrit tous les fichiers requis pour un server."""
    (node_dir / "netplan.yaml").write_text(_NETPLAN_VALID)
    (node_dir / "sysctl.conf").write_text(_SYSCTL_VALID)
    (node_dir / "dnsmasq.conf").write_text(_DNSMASQ_VALID)
    (node_dir / "k3s-config.yaml").write_text(k3s_content)
    (node_dir / "registries.yaml").write_text(_REGISTRIES_VALID)
    # meta.yaml pour get_kind
    (node_dir / "meta.yaml").write_text("kind: server\n")


def _write_agent_files(node_dir: Path, k3s_content: str = _K3S_CONFIG_AGENT_VALID) -> None:
    """Écrit tous les fichiers requis pour un agent."""
    (node_dir / "k3s-config.yaml").write_text(k3s_content)
    (node_dir / "registries.yaml").write_text(_REGISTRIES_VALID)
    # node-profile.yaml nécessite le catalog — on le mocke via patch
    (node_dir / "node-profile.yaml").write_text(_NODE_PROFILE_VALID)
    # meta.yaml pour get_kind
    (node_dir / "meta.yaml").write_text("kind: agent\n")


class TestRequiredFilesServer:
    def test_missing_required_files_returns_false(self, tmp_path):
        """Un node dir server vide doit échouer la validation."""
        (tmp_path / "meta.yaml").write_text("kind: server\n")
        from src.core.validate import validate_node_dir
        result = validate_node_dir(tmp_path, kind="server")
        assert result is False

    def test_partial_missing_returns_false(self, tmp_path):
        """Si un seul fichier requis manque, la validation doit échouer."""
        (tmp_path / "meta.yaml").write_text("kind: server\n")
        (tmp_path / "netplan.yaml").write_text(_NETPLAN_VALID)
        (tmp_path / "sysctl.conf").write_text(_SYSCTL_VALID)
        # dnsmasq.conf, k3s-config.yaml, registries.yaml manquants
        from src.core.validate import validate_node_dir
        result = validate_node_dir(tmp_path, kind="server")
        assert result is False

    def test_all_required_files_present_passes(self, tmp_path):
        """Tous les fichiers requis présents avec contenu valide doivent passer."""
        _write_server_files(tmp_path)
        from src.core.validate import validate_node_dir
        # dnsmasq.conf n'a pas de validateur enregistré, donc seuls netplan/sysctl/k3s sont vérifiés
        result = validate_node_dir(tmp_path, kind="server")
        assert result is True

    def test_kind_inferred_from_meta(self, tmp_path):
        """Sans kind explicite, get_kind() lit meta.yaml et applique les règles server."""
        (tmp_path / "meta.yaml").write_text("kind: server\n")
        from src.core.validate import validate_node_dir
        # Sans fichiers requis, doit échouer
        result = validate_node_dir(tmp_path)
        assert result is False


class TestRequiredFilesAgent:
    def test_missing_k3s_config_fails(self, tmp_path):
        """Un agent sans k3s-config.yaml doit échouer."""
        (tmp_path / "meta.yaml").write_text("kind: agent\n")
        (node_dir := tmp_path)
        (node_dir / "registries.yaml").write_text(_REGISTRIES_VALID)
        (node_dir / "node-profile.yaml").write_text(_NODE_PROFILE_VALID)
        # k3s-config.yaml manquant
        from src.core.validate import validate_node_dir
        result = validate_node_dir(tmp_path, kind="agent")
        assert result is False

    def test_missing_registries_fails(self, tmp_path):
        """Un agent sans registries.yaml doit échouer."""
        (tmp_path / "meta.yaml").write_text("kind: agent\n")
        (tmp_path / "k3s-config.yaml").write_text(_K3S_CONFIG_AGENT_VALID)
        (tmp_path / "node-profile.yaml").write_text(_NODE_PROFILE_VALID)
        # registries.yaml manquant
        from src.core.validate import validate_node_dir
        result = validate_node_dir(tmp_path, kind="agent")
        assert result is False

    def test_all_required_agent_files_present_passes(self, tmp_path):
        """Tous les fichiers agent requis avec contenu valide doivent passer."""
        _write_agent_files(tmp_path)
        from src.core.validate import validate_node_dir
        # node-profile.yaml nécessite le catalog — on patche load_catalog
        with patch("src.core.validate.load_catalog", return_value={}), \
             patch("src.core.validate.validate_profile", return_value=[]):
            result = validate_node_dir(tmp_path, kind="agent")
        assert result is True


class TestGetKindExceptionHandling:
    """Non-régression sur la gestion d'exception dans validate_node_dir."""

    def test_oserror_on_get_kind_logs_and_continues(self, tmp_path):
        """OSError lors de get_kind → kind=None, pas d'exception remontée."""
        from src.core.validate import validate_node_dir

        with patch("src.core.validate.get_kind", side_effect=OSError("permission denied")):
            # Sans fichiers connus, retourne False mais ne lève pas d'exception
            result = validate_node_dir(tmp_path)
        assert result is False  # aucun fichier à valider → False attendu

    def test_unexpected_exception_on_get_kind_propagates(self, tmp_path):
        """RuntimeError (bug inattendu) doit remonter — ne pas être silencieux."""
        from src.core.validate import validate_node_dir

        with patch("src.core.validate.get_kind", side_effect=RuntimeError("bug inattendu")):
            with pytest.raises(RuntimeError, match="bug inattendu"):
                validate_node_dir(tmp_path)

    def test_oserror_stderr_contains_path(self, tmp_path, capsys):
        """Le message d'erreur loggé doit mentionner le node_dir."""
        from src.core.validate import validate_node_dir

        with patch("src.core.validate.get_kind", side_effect=OSError("no such file")):
            validate_node_dir(tmp_path)

        captured = capsys.readouterr()
        assert str(tmp_path) in captured.err or str(tmp_path) in captured.out


class TestValidateCLIRequiredFiles:
    """Issue 4 — la commande CLI validate doit aussi vérifier les fichiers requis."""

    def test_cli_run_fails_on_missing_required_file(self, tmp_path):
        """La commande validate CLI doit échouer si un fichier requis manque."""
        import types
        from src.core.validate import run as validate_run
        from src.system.base import NODES_DIR

        node_dir = tmp_path / "r2arm01"
        node_dir.mkdir()
        # Simule kind=agent sans les fichiers requis
        (node_dir / "meta.yaml").write_text("kind: agent\n")

        args = types.SimpleNamespace(hostname="r2arm01", files=None)

        with patch("src.core.validate.NODES_DIR", tmp_path), \
             patch("src.core.validate.get_kind", return_value="agent"):
            with pytest.raises(SystemExit) as exc:
                validate_run(args)
        assert exc.value.code == 1

    def test_cli_run_no_required_files_for_unknown_kind(self, tmp_path):
        """Si le kind est inconnu, la CLI passe aux validateurs de contenu."""
        import types
        from src.core.validate import run as validate_run

        node_dir = tmp_path / "r2unknown"
        node_dir.mkdir()

        args = types.SimpleNamespace(hostname="r2unknown", files=None)

        with patch("src.core.validate.NODES_DIR", tmp_path), \
             patch("src.core.validate.get_kind", return_value="unknown"):
            with pytest.raises(SystemExit) as exc:
                validate_run(args)
        # Pas de fichiers à valider → exit(1)
        assert exc.value.code == 1


class TestSSHQuoting:
    def test_ssh_quote_handles_spaces(self):
        from src.system.subprocess_utils import ssh_quote
        assert ssh_quote("path with spaces") == "'path with spaces'"

    def test_ssh_quote_handles_special_chars(self):
        from src.system.subprocess_utils import ssh_quote
        assert ssh_quote("host; rm -rf /") == "'host; rm -rf /'"

    def test_ssh_quote_normal_string(self):
        from src.system.subprocess_utils import ssh_quote
        # Un token simple sans caractères spéciaux est retourné tel quel
        assert ssh_quote("r2arm01") == "r2arm01"

    def test_ssh_quote_empty_string(self):
        from src.system.subprocess_utils import ssh_quote
        assert ssh_quote("") == "''"
