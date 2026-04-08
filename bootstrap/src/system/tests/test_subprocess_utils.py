"""
Tests unitaires — src.system.subprocess_utils

Couvre :
- push_file : quoting robuste de remote_path avec shlex.quote
  (anti-régression : remote_path avec espaces ou apostrophes ne doit pas
   casser la commande 'sudo tee' distante)
"""
from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from src.system.subprocess_utils import CommandError, push_file


class TestPushFile:
    """Vérifie que remote_path est correctement quoté dans la commande SSH."""

    def _capture_ssh_cmd(self, remote_path: str) -> list[str]:
        """Lance push_file et retourne la commande SSH construite."""
        captured = {}

        def fake_run(cmd, **kwargs):
            captured["cmd"] = cmd
            return MagicMock(returncode=0)

        with patch("src.system.subprocess_utils.subprocess.run", side_effect=fake_run):
            push_file("user@host", remote_path, "content")

        return captured["cmd"]

    def test_standard_path_reaches_tee(self):
        cmd = self._capture_ssh_cmd("/etc/rancher/k3s/config.yaml")
        remote_part = cmd[-1]
        assert "tee" in remote_part
        assert "/etc/rancher/k3s/config.yaml" in remote_part

    def test_path_with_spaces_is_quoted(self):
        import shlex
        path = "/etc/r2bewi/nodes/my node/config.yaml"
        cmd = self._capture_ssh_cmd(path)
        remote_part = cmd[-1]
        # shlex.quote wraps the whole path in single quotes
        assert shlex.quote(path) in remote_part

    def test_path_with_single_quote_is_safe(self):
        """Un chemin avec apostrophe ne doit pas casser la commande distante."""
        cmd = self._capture_ssh_cmd("/tmp/it's/here")
        remote_part = cmd[-1]
        # shlex.quote représente l'apostrophe comme '"'"'
        assert "tee" in remote_part
        # Le chemin ne doit pas contenir de quote non échappée au milieu
        assert "sudo tee '/tmp/it's/here'" not in remote_part

    def test_path_without_special_chars_unquoted_or_safely_quoted(self):
        cmd = self._capture_ssh_cmd("/etc/hosts")
        remote_part = cmd[-1]
        assert "/etc/hosts" in remote_part

    def test_identity_forwarded(self):
        """L'option -i doit être présente quand identity est fourni."""
        captured = {}

        def fake_run(cmd, **kwargs):
            captured["cmd"] = cmd
            return MagicMock(returncode=0)

        with patch("src.system.subprocess_utils.subprocess.run", side_effect=fake_run):
            push_file("user@host", "/etc/test", "content", identity="/home/iobewi/.ssh/id_ed25519")

        assert "-i" in captured["cmd"]
        assert "/home/iobewi/.ssh/id_ed25519" in captured["cmd"]

    def test_raises_commanderror_on_nonzero_returncode(self):
        with patch("src.system.subprocess_utils.subprocess.run",
                   return_value=MagicMock(returncode=1, stderr="")):
            with pytest.raises(CommandError) as exc_info:
                push_file("user@host", "/etc/test", "content")
        assert exc_info.value.returncode == 1
        assert "tee" in str(exc_info.value) or "/etc/test" in str(exc_info.value)

    def test_commanderror_propagates_stderr(self):
        """Le stderr SSH réel doit être visible dans CommandError."""
        remote_stderr = "sudo: /etc/test: Permission denied"
        with patch("src.system.subprocess_utils.subprocess.run",
                   return_value=MagicMock(returncode=1, stderr=remote_stderr)):
            with pytest.raises(CommandError) as exc_info:
                push_file("user@host", "/etc/test", "content")
        assert exc_info.value.stderr == remote_stderr
        assert "Permission denied" in str(exc_info.value)

    def test_capture_output_enabled(self):
        """subprocess.run doit être appelé avec capture_output=True pour récupérer stderr."""
        call_kwargs = {}

        def fake_run(cmd, **kwargs):
            call_kwargs.update(kwargs)
            return MagicMock(returncode=0, stderr="")

        with patch("src.system.subprocess_utils.subprocess.run", side_effect=fake_run):
            push_file("user@host", "/etc/test", "content")

        assert call_kwargs.get("capture_output") is True


class TestRunTimeout:
    def test_timeout_raises_commanderror(self):
        from src.system.subprocess_utils import run, CommandError
        with patch("src.system.subprocess_utils.subprocess.run",
                   side_effect=subprocess.TimeoutExpired(cmd=["sleep"], timeout=5)):
            with pytest.raises(CommandError) as exc_info:
                run(["sleep", "999"], timeout=5)
        assert exc_info.value.returncode == -1
        assert "5s" in str(exc_info.value)

    def test_timeout_message_contains_hint(self):
        from src.system.subprocess_utils import run, CommandError
        with patch("src.system.subprocess_utils.subprocess.run",
                   side_effect=subprocess.TimeoutExpired(cmd=["apt-get"], timeout=120)):
            with pytest.raises(CommandError) as exc_info:
                run(["apt-get", "upgrade"], timeout=120)
        assert "120s" in exc_info.value.stderr

    def test_no_timeout_passes_none_to_subprocess(self):
        call_kwargs = {}
        def fake_run(cmd, **kwargs):
            call_kwargs.update(kwargs)
            return MagicMock(returncode=0, stderr="")
        with patch("src.system.subprocess_utils.subprocess.run", side_effect=fake_run):
            from src.system.subprocess_utils import run
            run(["echo", "ok"])
        assert call_kwargs.get("timeout") is None

    def test_timeout_forwarded_to_subprocess(self):
        call_kwargs = {}
        def fake_run(cmd, **kwargs):
            call_kwargs.update(kwargs)
            return MagicMock(returncode=0, stderr="")
        with patch("src.system.subprocess_utils.subprocess.run", side_effect=fake_run):
            from src.system.subprocess_utils import run
            run(["echo", "ok"], timeout=30)
        assert call_kwargs["timeout"] == 30


class TestPushFileTimeout:
    def test_timeout_raises_commanderror(self):
        from src.system.subprocess_utils import push_file, CommandError
        with patch("src.system.subprocess_utils.subprocess.run",
                   side_effect=subprocess.TimeoutExpired(cmd=["ssh"], timeout=60)):
            with pytest.raises(CommandError) as exc_info:
                push_file("user@host", "/etc/test", "content", timeout=60)
        assert exc_info.value.returncode == -1
        assert "60s" in exc_info.value.stderr


class TestSshQuote:
    """Vérifie que ssh_quote protège contre l'injection shell."""

    def test_quotes_spaces(self):
        from src.system.subprocess_utils import ssh_quote
        result = ssh_quote("path with spaces")
        assert result == "'path with spaces'"

    def test_quotes_injection(self):
        from src.system.subprocess_utils import ssh_quote
        result = ssh_quote("host; rm -rf /")
        # Le résultat doit être enveloppé dans des guillemets simples pour neutraliser le ;
        assert result == "'host; rm -rf /'"
        # Le résultat commence et finit par un guillemet simple
        assert result.startswith("'") and result.endswith("'")

    def test_passthrough_safe(self):
        from src.system.subprocess_utils import ssh_quote
        # Un token alphanumérique simple ne doit pas être modifié
        result = ssh_quote("r2arm01")
        assert result == "r2arm01"


class TestRunErrors:
    """Tests pour run() — chemins d'erreur subprocess."""

    def test_run_raises_on_nonzero_with_check(self):
        """check=True + returncode != 0 → CommandError levée."""
        from src.system.subprocess_utils import run, CommandError
        with patch("src.system.subprocess_utils.subprocess.run",
                   return_value=MagicMock(returncode=1, stdout="", stderr="error msg")):
            with pytest.raises(CommandError) as exc_info:
                run(["false"], check=True)
        assert exc_info.value.returncode == 1

    def test_run_no_raise_on_nonzero_without_check(self):
        """check=False + returncode != 0 → pas d'exception."""
        from src.system.subprocess_utils import run
        with patch("src.system.subprocess_utils.subprocess.run",
                   return_value=MagicMock(returncode=1, stdout="", stderr="")):
            result = run(["false"], check=False)
        assert result.returncode == 1

    def test_run_captures_stdout(self):
        """capture=True → stdout disponible dans le résultat."""
        from src.system.subprocess_utils import run
        with patch("src.system.subprocess_utils.subprocess.run",
                   return_value=MagicMock(returncode=0, stdout="hello\n", stderr="")) as mock_sp:
            result = run(["echo", "hello"], capture=True)
        # Verify subprocess.run was called with PIPE
        import subprocess
        call_kwargs = mock_sp.call_args
        assert call_kwargs.kwargs.get("stdout") == subprocess.PIPE
        assert result.stdout == "hello\n"

    def test_run_zero_returncode_no_raise_with_check(self):
        """check=True + returncode == 0 → pas d'exception."""
        from src.system.subprocess_utils import run
        with patch("src.system.subprocess_utils.subprocess.run",
                   return_value=MagicMock(returncode=0, stdout="", stderr="")):
            result = run(["true"], check=True)
        assert result.returncode == 0

    def test_run_passes_input(self):
        """input fourni → transmis à subprocess.run."""
        from src.system.subprocess_utils import run
        with patch("src.system.subprocess_utils.subprocess.run",
                   return_value=MagicMock(returncode=0, stdout="PUBKEY", stderr="")) as mock_sp:
            run(["wg", "pubkey"], input="PRIVKEY", capture=True)
        call_kwargs = mock_sp.call_args
        assert call_kwargs.kwargs.get("input") == "PRIVKEY"


class TestRunSshErrors:
    """Tests pour run_ssh() — chemins d'erreur SSH."""

    def test_run_ssh_nonzero_raises_with_check(self):
        """SSH returncode != 0 + check=True → CommandError."""
        from src.system.subprocess_utils import run_ssh, CommandError
        with patch("src.system.subprocess_utils.subprocess.run",
                   return_value=MagicMock(returncode=255, stdout="", stderr="Connection refused")):
            with pytest.raises(CommandError) as exc_info:
                run_ssh("user@host", "ls /", check=True)
        assert exc_info.value.returncode == 255

    def test_run_ssh_no_raise_without_check(self):
        """SSH returncode != 0 + check=False → pas d'exception."""
        from src.system.subprocess_utils import run_ssh
        with patch("src.system.subprocess_utils.subprocess.run",
                   return_value=MagicMock(returncode=1, stdout="", stderr="")):
            result = run_ssh("user@host", "ls /nonexistent", check=False)
        assert result.returncode == 1

    def test_run_ssh_with_identity(self):
        """identity fourni → -i <path> dans la commande SSH."""
        from src.system.subprocess_utils import run_ssh
        with patch("src.system.subprocess_utils.subprocess.run",
                   return_value=MagicMock(returncode=0, stdout="", stderr="")) as mock_sp:
            run_ssh("user@host", "uptime", identity="/home/user/.ssh/id_ed25519", check=True)
        cmd = mock_sp.call_args[0][0]
        assert "-i" in cmd
        assert "/home/user/.ssh/id_ed25519" in cmd

    def test_run_ssh_without_identity_no_dash_i(self):
        """Sans identity, -i n'apparaît pas dans la commande SSH."""
        from src.system.subprocess_utils import run_ssh
        with patch("src.system.subprocess_utils.subprocess.run",
                   return_value=MagicMock(returncode=0, stdout="", stderr="")) as mock_sp:
            run_ssh("user@host", "uptime", check=True)
        cmd = mock_sp.call_args[0][0]
        assert "-i" not in cmd

    def test_run_ssh_includes_target_and_command(self):
        """La cible et la commande distante sont dans le cmd SSH."""
        from src.system.subprocess_utils import run_ssh
        with patch("src.system.subprocess_utils.subprocess.run",
                   return_value=MagicMock(returncode=0, stdout="", stderr="")) as mock_sp:
            run_ssh("root@192.168.1.1", "hostname", check=True)
        cmd = mock_sp.call_args[0][0]
        assert "root@192.168.1.1" in cmd
        assert "hostname" in cmd

    def test_run_ssh_tty_adds_t_flag(self):
        """tty=True ajoute -t dans la commande SSH."""
        from src.system.subprocess_utils import run_ssh
        with patch("src.system.subprocess_utils.subprocess.run",
                   return_value=MagicMock(returncode=0, stdout="", stderr="")) as mock_sp:
            run_ssh("user@host", "sudo bash", tty=True, check=True)
        cmd = mock_sp.call_args[0][0]
        assert "-t" in cmd
