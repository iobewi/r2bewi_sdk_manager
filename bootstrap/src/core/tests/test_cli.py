"""
Tests de non-régression — CLI

Couvre :
- parsing de toutes les sous-commandes
- dispatch vers les bons modules (parametrize)
- assertions de kwargs pour les cas avec options
- commande init (rendu dans /etc/r2bewi/nodes/<hostname>/)
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from src.cli import build_parser, main


# ── Parser ────────────────────────────────────────────────────────────────────

class TestParser:
    def test_unknown_command_exits(self):
        parser = build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["unknown-cmd"])

    # init
    def test_init_parser_minimal(self):
        parser = build_parser()
        args = parser.parse_args(["init", "r2arm01", "--kind", "agent"])
        assert args.command == "init"
        assert args.hostname == "r2arm01"
        assert args.kind == "agent"
        assert args.ip is None
        assert args.ssh_user is None

    def test_init_parser_server(self):
        parser = build_parser()
        args = parser.parse_args(["init", "r2bewi", "--kind", "server", "--ip", "192.168.82.1"])
        assert args.hostname == "r2bewi"
        assert args.kind == "server"
        assert args.ip == "192.168.82.1"

    def test_init_kind_required(self):
        parser = build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["init", "r2arm01"])

    def test_init_hostname_required(self):
        parser = build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["init", "--kind", "agent"])

    # deploy
    def test_deploy_parser_local(self):
        parser = build_parser()
        args = parser.parse_args(["deploy", "r2bewi"])
        assert args.command == "deploy"
        assert args.hostname == "r2bewi"
        assert args.ip is None
        assert args.ssh_user is None  # None = non fourni, résolu depuis meta.yaml ou défaut

    def test_deploy_parser_remote(self):
        parser = build_parser()
        args = parser.parse_args(["deploy", "r2arm01", "--ip", "192.168.82.10"])
        assert args.ip == "192.168.82.10"

    def test_deploy_parser_registry_size_default(self):
        parser = build_parser()
        args = parser.parse_args(["deploy", "r2bewi"])
        assert args.registry_size == "256G"

    def test_deploy_parser_registry_size_custom(self):
        parser = build_parser()
        args = parser.parse_args(["deploy", "r2bewi", "--registry-size", "128G"])
        assert args.registry_size == "128G"

    # enroll
    def test_enroll_parser_minimal(self):
        parser = build_parser()
        args = parser.parse_args(["enroll", "r2bewi"])
        assert args.command == "enroll"
        assert args.hostname == "r2bewi"
        assert args.ip is None
        assert args.bootstrap_user is None
        assert args.nvidia is False

    def test_enroll_parser_agent(self):
        parser = build_parser()
        args = parser.parse_args([
            "enroll", "r2arm01",
            "--ip", "192.168.82.10",
            "--bootstrap-user", "ubuntu",
            "--nvidia",
        ])
        assert args.ip == "192.168.82.10"
        assert args.bootstrap_user == "ubuntu"
        assert args.nvidia is True

    # status
    def test_status_parser_minimal(self):
        parser = build_parser()
        args = parser.parse_args(["status", "r2bewi"])
        assert args.command == "status"
        assert args.hostname == "r2bewi"
        assert args.ip is None
        assert args.ssh_user == "iobewi"

    def test_status_parser_with_ip(self):
        parser = build_parser()
        args = parser.parse_args(["status", "r2arm01", "--ip", "192.168.82.10"])
        assert args.ip == "192.168.82.10"

    # validate
    def test_validate_parser_minimal(self):
        parser = build_parser()
        args = parser.parse_args(["validate", "r2arm01"])
        assert args.command == "validate"
        assert args.hostname == "r2arm01"
        assert args.files is None

    def test_validate_parser_with_file(self):
        parser = build_parser()
        args = parser.parse_args(["validate", "r2arm01", "--file", "node-profile.yaml"])
        assert args.files == ["node-profile.yaml"]

    def test_validate_parser_multiple_files(self):
        parser = build_parser()
        args = parser.parse_args(["validate", "r2arm01", "--file", "node-profile.yaml", "k3s-config.yaml"])
        assert args.files == ["node-profile.yaml", "k3s-config.yaml"]

    # render-labels
    def test_render_labels_parser(self):
        parser = build_parser()
        args = parser.parse_args(["render-labels", "r2arm01"])
        assert args.command == "render-labels"
        assert args.hostname == "r2arm01"

    # update
    def test_update_parser(self):
        parser = build_parser()
        args = parser.parse_args(["update", "r2arm01"])
        assert args.command == "update"
        assert args.hostname == "r2arm01"

    # uninstall
    def test_uninstall_parser_minimal(self):
        parser = build_parser()
        args = parser.parse_args(["uninstall", "r2bewi"])
        assert args.command == "uninstall"
        assert args.hostname == "r2bewi"
        assert args.ip is None
        assert args.ssh_user == "iobewi"

    def test_uninstall_parser_agent(self):
        parser = build_parser()
        args = parser.parse_args(["uninstall", "r2arm01", "--ip", "192.168.82.10", "--ssh-user", "pi"])
        assert args.ip == "192.168.82.10"
        assert args.ssh_user == "pi"


# ── Dispatch ──────────────────────────────────────────────────────────────────

def _dispatch_mock(argv: list[str], patch_target: str):
    """Lance main() avec argv donné, mock le run cible, retourne le mock."""
    with patch("sys.argv", argv):
        with patch(patch_target) as mock:
            mock.side_effect = SystemExit(0)
            with pytest.raises(SystemExit):
                main()
    return mock


class TestDispatch:
    """Vérifie que chaque sous-commande CLI atteint le bon module run."""

    @pytest.mark.parametrize("argv,patch_target", [
        (["r2bewi", "deploy",        "r2bewi"],   "src.core.deploy.run"),
        (["r2bewi", "enroll",        "r2bewi"],   "src.components.k3s.enroll.run"),
        (["r2bewi", "status",        "r2bewi"],   "src.core.status.run"),
        (["r2bewi", "validate",      "r2arm01"],  "src.core.validate.run"),
        (["r2bewi", "render-labels", "r2arm01"],  "src.components.k3s.render_labels.run"),
        (["r2bewi", "update",        "r2arm01"],  "src.components.k3s.update.run"),
        (["r2bewi", "uninstall",     "r2bewi"],   "src.components.k3s.uninstall.run"),
    ])
    def test_command_reaches_module(self, argv, patch_target):
        mock = _dispatch_mock(argv, patch_target)
        mock.assert_called_once()

    # ── kwargs forwarding via args ────────────────────────────────────────────

    def test_deploy_forwards_ip(self):
        mock = _dispatch_mock(
            ["r2bewi", "deploy", "r2arm01", "--ip", "192.168.82.10"],
            "src.core.deploy.run",
        )
        assert mock.call_args[0][0].ip == "192.168.82.10"

    def test_deploy_ip_none_when_local(self):
        mock = _dispatch_mock(["r2bewi", "deploy", "r2bewi"], "src.core.deploy.run")
        assert mock.call_args[0][0].ip is None

    def test_enroll_forwards_ip(self):
        mock = _dispatch_mock(
            ["r2bewi", "enroll", "r2arm01", "--ip", "192.168.82.10"],
            "src.components.k3s.enroll.run",
        )
        assert mock.call_args[0][0].ip == "192.168.82.10"

    def test_enroll_ip_none_when_server(self):
        mock = _dispatch_mock(["r2bewi", "enroll", "r2bewi"], "src.components.k3s.enroll.run")
        assert mock.call_args[0][0].ip is None

    def test_status_forwards_ip(self):
        mock = _dispatch_mock(
            ["r2bewi", "status", "r2arm01", "--ip", "192.168.82.10"],
            "src.core.status.run",
        )
        assert mock.call_args[0][0].ip == "192.168.82.10"

    def test_uninstall_forwards_ip(self):
        mock = _dispatch_mock(
            ["r2bewi", "uninstall", "r2arm01", "--ip", "192.168.82.10"],
            "src.components.k3s.uninstall.run",
        )
        assert mock.call_args[0][0].ip == "192.168.82.10"

    def test_uninstall_forwards_ssh_user(self):
        mock = _dispatch_mock(
            ["r2bewi", "uninstall", "r2arm01", "--ip", "192.168.82.10", "--ssh-user", "pi"],
            "src.components.k3s.uninstall.run",
        )
        assert mock.call_args[0][0].ssh_user == "pi"

    def test_status_forwards_ssh_user(self):
        mock = _dispatch_mock(
            ["r2bewi", "status", "r2arm01", "--ip", "192.168.82.10", "--ssh-user", "pi"],
            "src.core.status.run",
        )
        assert mock.call_args[0][0].ssh_user == "pi"


# ── Propagation ssh_user dans uninstall ───────────────────────────────────────

class TestUninstallSshUser:
    """Vérifie que ssh_user est bien transmis à ssh_target."""

    def _run(self, tmp_path, ssh_user_arg=None):
        node_dir = tmp_path / "r2arm01"
        node_dir.mkdir()

        with patch("src.components.k3s.uninstall.NODES_DIR", tmp_path), \
             patch("src.components.k3s.uninstall.get_kind", return_value="agent"), \
             patch("src.components.k3s.uninstall.resolve_ip", return_value="192.168.82.10"), \
             patch("src.components.k3s.uninstall._uninstall_agent") as mock_agent, \
             patch("src.components.k3s.uninstall.ssh_target", return_value="iobewi@192.168.82.10") as mock_ssh_target, \
             patch("src.components.k3s.uninstall.resolve_ssh_user",
                   wraps=lambda node_dir, cli_user, default="iobewi": cli_user) as mock_resolve:

            from src.components.k3s.uninstall import run
            import argparse
            args = argparse.Namespace(
                hostname="r2arm01",
                ip="192.168.82.10",
                ssh_user=ssh_user_arg if ssh_user_arg is not None else "iobewi",
            )
            run(args)

            return mock_resolve, mock_ssh_target, mock_agent

    def test_custom_ssh_user_reaches_ssh_target(self, tmp_path):
        mock_resolve, mock_ssh_target, _ = self._run(tmp_path, ssh_user_arg="pi")
        mock_resolve.assert_called_once()
        args, _ = mock_resolve.call_args
        assert args[1] == "pi", "resolve_ssh_user doit recevoir le user CLI"
        called_user = mock_ssh_target.call_args[0][2]
        assert called_user == "pi", f"ssh_target doit utiliser 'pi', reçu : {called_user!r}"

    def test_default_ssh_user_is_iobewi(self, tmp_path):
        mock_resolve, mock_ssh_target, _ = self._run(tmp_path)
        called_user = mock_ssh_target.call_args[0][2]
        assert called_user == "iobewi", f"ssh_target doit utiliser 'iobewi' par défaut, reçu : {called_user!r}"


# ── Commande init ─────────────────────────────────────────────────────────────

class TestInitCommand:
    def test_init_agent_creates_node_dir(self, tmp_path):
        nodes_dir = tmp_path / "nodes"
        with patch("src.core.init.NODES_DIR", nodes_dir):
            with patch("sys.argv", ["r2bewi", "init", "r2arm01", "--kind", "agent"]):
                main()
        assert (nodes_dir / "r2arm01").is_dir()

    def test_init_agent_creates_expected_files(self, tmp_path):
        nodes_dir = tmp_path / "nodes"
        with patch("src.core.init.NODES_DIR", nodes_dir):
            with patch("sys.argv", ["r2bewi", "init", "r2arm01", "--kind", "agent"]):
                main()
        node_dir = nodes_dir / "r2arm01"
        assert (node_dir / "k3s-config.yaml").exists()
        assert (node_dir / "registries.yaml").exists()
        assert (node_dir / "node-profile.yaml").exists()

    def test_init_server_creates_expected_files(self, tmp_path):
        nodes_dir = tmp_path / "nodes"
        with patch("src.core.init.NODES_DIR", nodes_dir):
            with patch("sys.argv", ["r2bewi", "init", "r2bewi", "--kind", "server",
                                     "--ip", "192.168.82.1"]):
                main()
        node_dir = nodes_dir / "r2bewi"
        assert (node_dir / "k3s-config.yaml").exists()
        assert (node_dir / "registries.yaml").exists()
        assert (node_dir / "netplan.yaml").exists()
        assert (node_dir / "sysctl.conf").exists()
        assert (node_dir / "dnsmasq.conf").exists()

    def test_init_agent_token_placeholder(self, tmp_path):
        nodes_dir = tmp_path / "nodes"
        with patch("src.core.init.NODES_DIR", nodes_dir):
            with patch("sys.argv", ["r2bewi", "init", "r2arm01", "--kind", "agent"]):
                main()
        content = (nodes_dir / "r2arm01" / "k3s-config.yaml").read_text()
        assert "__TOKEN__" in content

    def test_init_agent_server_url_uses_dns(self, tmp_path):
        nodes_dir = tmp_path / "nodes"
        with patch("src.core.init.NODES_DIR", nodes_dir):
            with patch("sys.argv", ["r2bewi", "init", "r2arm01", "--kind", "agent"]):
                main()
        content = (nodes_dir / "r2arm01" / "k3s-config.yaml").read_text()
        assert "k3s.r2bewi.internal" in content

    def test_init_agent_no_ip_still_creates_files(self, tmp_path):
        nodes_dir = tmp_path / "nodes"
        with patch("src.core.init.NODES_DIR", nodes_dir):
            with patch("sys.argv", ["r2bewi", "init", "r2arm01", "--kind", "agent"]):
                main()
        assert (nodes_dir / "r2arm01" / "k3s-config.yaml").exists()

    def test_init_invalid_hostname_exits_1(self, tmp_path):
        nodes_dir = tmp_path / "nodes"
        with patch("src.core.init.NODES_DIR", nodes_dir):
            with patch("sys.argv", ["r2bewi", "init", "r2arm_01", "--kind", "agent"]):
                with pytest.raises(SystemExit) as exc:
                    main()
        assert exc.value.code == 1

    def test_init_invalid_hostname_error_message(self, tmp_path, capsys):
        nodes_dir = tmp_path / "nodes"
        with patch("src.core.init.NODES_DIR", nodes_dir):
            with patch("sys.argv", ["r2bewi", "init", "bad_name", "--kind", "agent"]):
                with pytest.raises(SystemExit):
                    main()
        err = capsys.readouterr().err
        assert "hostname" in err.lower() or "invalide" in err.lower()

    def test_init_server_ip_in_tls_san(self, tmp_path):
        nodes_dir = tmp_path / "nodes"
        with patch("src.core.init.NODES_DIR", nodes_dir):
            with patch("sys.argv", ["r2bewi", "init", "r2bewi", "--kind", "server",
                                     "--ip", "10.0.0.1"]):
                main()
        content = (nodes_dir / "r2bewi" / "k3s-config.yaml").read_text()
        assert "10.0.0.1" in content


# ── Intégration source ────────────────────────────────────────────────────────

class TestSourceExecution:
    """Vérifie que la CLI fonctionne depuis la source (python -m bootstrap.src)."""

    def test_help_from_source(self):
        """python -m bootstrap.src --help doit afficher l'aide sans erreur d'import."""
        repo_root = Path(__file__).parents[4]  # /workspace
        result = subprocess.run(
            [sys.executable, "-m", "bootstrap.src", "--help"],
            capture_output=True, text=True, cwd=repo_root,
        )
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert "r2bewi" in result.stdout
        assert "deploy" in result.stdout
        assert "enroll" in result.stdout

    def test_all_commands_visible_from_source(self):
        """Toutes les commandes composants doivent apparaître dans --help."""
        repo_root = Path(__file__).parents[4]
        result = subprocess.run(
            [sys.executable, "-m", "bootstrap.src", "--help"],
            capture_output=True, text=True, cwd=repo_root,
        )
        assert result.returncode == 0
        for cmd in ("enroll", "wg-peer", "headlamp-token", "uninstall"):
            assert cmd in result.stdout, f"commande manquante dans --help : {cmd}"


# ── Smoke test binaire ────────────────────────────────────────────────────────

class TestSmokeBinary:
    """Smoke tests du binaire packagé (zipapp)."""

    @pytest.mark.skipif(
        not Path(__file__).parents[3].joinpath("dist/r2bewi").exists(),
        reason="binaire dist/r2bewi absent — lancer make build d'abord"
    )
    def test_binary_help(self):
        """Le binaire packagé répond à --help sans erreur."""
        binary = Path(__file__).parents[3] / "dist" / "r2bewi"
        result = subprocess.run(
            [str(binary), "--help"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        assert "r2bewi" in result.stdout
        assert "deploy" in result.stdout
