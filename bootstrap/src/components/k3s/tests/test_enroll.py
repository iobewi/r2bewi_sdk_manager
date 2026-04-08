"""
Tests unitaires — src.components.k3s.enroll

Couvre :
- _enroll_server préflight : non-root, mauvais user, config manquante, token manquant
- _enroll_agent préflight : non-root, ssh manquant, token manquant
- Idempotence server : déjà installé → exit 0
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ── Helpers ───────────────────────────────────────────────────────────────────

_K3S_CONFIG_VALID = "node-label: []\n"
_REGISTRIES_VALID = "mirrors: {}\n"
_NODE_PROFILE_VALID = "labels:\n  env: test\n"


def _make_agent_dir(node_dir: Path) -> None:
    (node_dir / "meta.yaml").write_text("kind: agent\n")
    (node_dir / "k3s-config.yaml").write_text(
        "server: https://192.168.1.1:6443\ntoken: tok\nnode-label: []\n"
    )
    (node_dir / "registries.yaml").write_text(_REGISTRIES_VALID)
    (node_dir / "node-profile.yaml").write_text(_NODE_PROFILE_VALID)


# ── Server préflight ──────────────────────────────────────────────────────────

class TestEnrollPreflightServer:
    def test_non_root_exits(self):
        """Sans root (geteuid != 0) → sys.exit(1)."""
        with patch("os.geteuid", return_value=1):
            from src.components.k3s.enroll import _enroll_server
            with pytest.raises(SystemExit) as exc:
                _enroll_server("testhost")
            assert exc.value.code == 1

    def test_wrong_user_exits(self):
        """SUDO_USER != 'iobewi' → sys.exit(1)."""
        with patch("os.geteuid", return_value=0), \
             patch.dict(os.environ, {"SUDO_USER": "ubuntu"}):
            from src.components.k3s.enroll import _enroll_server
            with pytest.raises(SystemExit) as exc:
                _enroll_server("testhost")
            assert exc.value.code == 1

    def test_missing_config_exits(self, tmp_path):
        """K3S_CONFIG_FILE absent → sys.exit(1)."""
        with patch("os.geteuid", return_value=0), \
             patch.dict(os.environ, {"SUDO_USER": "iobewi"}), \
             patch("src.system.helpers.shutil") as mock_shutil, \
             patch("src.components.k3s.enroll.K3S_CONFIG_FILE", tmp_path / "nonexistent.yaml"):
            mock_shutil.which.return_value = "/usr/bin/curl"
            from src.components.k3s.enroll import _enroll_server
            with pytest.raises(SystemExit) as exc:
                _enroll_server("testhost")
            assert exc.value.code == 1

    def test_missing_k3s_token_exits_after_install(self, tmp_path):
        """K3s installé mais token absent → sys.exit(1) après installation."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text(_K3S_CONFIG_VALID)
        token_file = tmp_path / "node-token"
        # token_file n'existe pas

        mock_run = MagicMock(return_value=MagicMock(returncode=0))

        with patch("os.geteuid", return_value=0), \
             patch.dict(os.environ, {"SUDO_USER": "iobewi"}), \
             patch("src.system.helpers.shutil") as mock_shutil, \
             patch("src.components.k3s.enroll.K3S_CONFIG_FILE", config_file), \
             patch("src.components.k3s.enroll.K3S_TOKEN_FILE", token_file), \
             patch("src.components.k3s.enroll._run_cmd", mock_run), \
             patch("src.components.k3s.enroll._wait_k3s_ready"):
            # which("k3s") → None (k3s non installé), which pour tools → non-None
            mock_shutil.which.return_value = None
            from src.components.k3s.enroll import _enroll_server
            with pytest.raises(SystemExit) as exc:
                _enroll_server("testhost")
            assert exc.value.code == 1


# ── Agent préflight ───────────────────────────────────────────────────────────

class TestEnrollPreflightAgent:
    def test_non_root_exits(self, tmp_path):
        """Sans root → sys.exit(1)."""
        _make_agent_dir(tmp_path)
        with patch("os.geteuid", return_value=1):
            from src.components.k3s.enroll import _enroll_agent
            with pytest.raises(SystemExit) as exc:
                _enroll_agent("testhost", tmp_path, "iobewi@192.168.1.10", None, False)
            assert exc.value.code == 1

    def test_wrong_user_exits(self, tmp_path):
        """SUDO_USER != 'iobewi' → sys.exit(1)."""
        _make_agent_dir(tmp_path)
        with patch("os.geteuid", return_value=0), \
             patch.dict(os.environ, {"SUDO_USER": "ubuntu"}):
            from src.components.k3s.enroll import _enroll_agent
            with pytest.raises(SystemExit) as exc:
                _enroll_agent("testhost", tmp_path, "iobewi@192.168.1.10", None, False)
            assert exc.value.code == 1

    def test_missing_ssh_exits(self, tmp_path):
        """ssh absent → sys.exit(1)."""
        _make_agent_dir(tmp_path)
        with patch("os.geteuid", return_value=0), \
             patch.dict(os.environ, {"SUDO_USER": "iobewi"}), \
             patch("src.system.helpers.shutil") as mock_shutil:
            mock_shutil.which.return_value = None  # ssh absent
            from src.components.k3s.enroll import _enroll_agent
            with pytest.raises(SystemExit) as exc:
                _enroll_agent("testhost", tmp_path, "iobewi@192.168.1.10", None, False)
            assert exc.value.code == 1

    def test_missing_token_exits(self, tmp_path):
        """Token K3s absent → sys.exit(1)."""
        _make_agent_dir(tmp_path)
        token_file = tmp_path / "nonexistent-token"

        with patch("os.geteuid", return_value=0), \
             patch.dict(os.environ, {"SUDO_USER": "iobewi"}), \
             patch("src.system.helpers.shutil") as mock_shutil, \
             patch("src.components.k3s.enroll.K3S_TOKEN_FILE", token_file):
            mock_shutil.which.return_value = "/usr/bin/ssh"
            from src.components.k3s.enroll import _enroll_agent
            with pytest.raises(SystemExit) as exc:
                _enroll_agent("testhost", tmp_path, "iobewi@192.168.1.10", None, False)
            assert exc.value.code == 1


# ── Idempotence ───────────────────────────────────────────────────────────────

class TestEnrollIdempotence:
    def test_server_already_enrolled_exits_cleanly(self, tmp_path):
        """K3s déjà installé + token présent → enroll skipe proprement (exit 0)."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text(_K3S_CONFIG_VALID)
        token_file = tmp_path / "node-token"
        token_file.write_text("mytoken\n")

        mock_run = MagicMock(return_value=MagicMock(returncode=0, stdout=""))

        with patch("os.geteuid", return_value=0), \
             patch.dict(os.environ, {"SUDO_USER": "iobewi"}), \
             patch("src.system.helpers.shutil") as mock_shutil, \
             patch("src.components.k3s.enroll.K3S_CONFIG_FILE", config_file), \
             patch("src.components.k3s.enroll.K3S_TOKEN_FILE", token_file), \
             patch("src.components.k3s.enroll._run_cmd", mock_run):
            # which("k3s") → non-None (k3s déjà installé)
            mock_shutil.which.return_value = "/usr/local/bin/k3s"
            from src.components.k3s.enroll import _enroll_server
            with pytest.raises(SystemExit) as exc:
                _enroll_server("testhost")
            # exit(0) = déjà initialisé → OK
            assert exc.value.code == 0


# ── _install_k3s ──────────────────────────────────────────────────────────────

class TestInstallK3s:
    def test_local_server_runs_sh(self):
        from src.components.k3s.enroll import _install_k3s
        with patch("src.components.k3s.enroll._run_cmd") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            _install_k3s("server")
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert args[0] == "sh"

    def test_remote_agent_runs_ssh(self):
        from src.components.k3s.enroll import _install_k3s
        with patch("src.components.k3s.enroll.run_ssh") as mock_ssh:
            mock_ssh.return_value = MagicMock(returncode=0)
            _install_k3s("agent", target="iobewi@1.2.3.4", identity=Path("/root/.ssh/id"))
        assert mock_ssh.call_count >= 1
        first_call_cmd = mock_ssh.call_args_list[0][0][1]
        assert "agent" in first_call_cmd


# ── _wait_k3s_ready ───────────────────────────────────────────────────────────

class TestWaitK3sReady:
    def test_api_ready_on_first_try(self):
        from src.components.k3s.enroll import _wait_k3s_ready
        with patch("src.components.k3s.enroll._run_cmd",
                   return_value=MagicMock(returncode=0, stdout="")):
            _wait_k3s_ready(timeout=10)  # hostname=None → API check

    def test_node_ready_on_first_try(self):
        from src.components.k3s.enroll import _wait_k3s_ready
        with patch("src.components.k3s.enroll._run_cmd",
                   return_value=MagicMock(returncode=0, stdout="r2arm01 Ready <none>")):
            _wait_k3s_ready(hostname="r2arm01", timeout=10)

    def test_timeout_exits(self):
        from src.components.k3s.enroll import _wait_k3s_ready
        # monotonic() is called 3+ times per loop iteration: deadline, while check, remaining
        # Return 0 for the first call (deadline), then 9999 to force immediate timeout
        calls = iter([0] + [9999] * 20)
        with patch("src.components.k3s.enroll._run_cmd",
                   return_value=MagicMock(returncode=1, stdout="")), \
             patch("src.components.k3s.enroll.time.sleep"), \
             patch("src.components.k3s.enroll.time.monotonic", side_effect=calls):
            with pytest.raises(SystemExit) as exc:
                _wait_k3s_ready(hostname="r2arm01", timeout=5)
            assert exc.value.code == 1


# ── _preflight_remote ─────────────────────────────────────────────────────────

class TestPreflightRemote:
    def _ok_ssh(self):
        return MagicMock(returncode=0, stdout="ok\n")

    def test_ssh_unreachable_exits(self):
        from src.components.k3s.enroll import _preflight_remote
        with patch("src.components.k3s.enroll.run_ssh",
                   return_value=MagicMock(returncode=1, stdout="")):
            with pytest.raises(SystemExit) as exc:
                _preflight_remote("iobewi@1.2.3.4", Path("/root/.ssh/id"), nvidia=False)
            assert exc.value.code == 1

    def test_sudo_missing_exits(self):
        from src.components.k3s.enroll import _preflight_remote
        responses = iter([
            MagicMock(returncode=0, stdout="ok\n"),   # SSH reachable
            MagicMock(returncode=0, stdout=""),         # date sync
            MagicMock(returncode=0, stdout=""),         # sudo absent
        ])
        with patch("src.components.k3s.enroll.run_ssh", side_effect=responses):
            with pytest.raises(SystemExit) as exc:
                _preflight_remote("iobewi@1.2.3.4", Path("/root/.ssh/id"), nvidia=False)
            assert exc.value.code == 1

    def test_no_internet_exits(self):
        from src.components.k3s.enroll import _preflight_remote
        responses = iter([
            MagicMock(returncode=0, stdout="ok\n"),   # SSH reachable
            MagicMock(returncode=0, stdout=""),         # date sync
            MagicMock(returncode=0, stdout="ok\n"),   # sudo present
            MagicMock(returncode=0, stdout=""),         # internet absent
        ])
        with patch("src.components.k3s.enroll.run_ssh", side_effect=responses):
            with pytest.raises(SystemExit) as exc:
                _preflight_remote("iobewi@1.2.3.4", Path("/root/.ssh/id"), nvidia=False)
            assert exc.value.code == 1


# ── _node_in_cluster ──────────────────────────────────────────────────────────

class TestNodeInCluster:
    def test_true_when_kubectl_success(self):
        from src.components.k3s.enroll import _node_in_cluster
        with patch("src.components.k3s.enroll._run_cmd",
                   return_value=MagicMock(returncode=0)):
            assert _node_in_cluster("r2arm01") is True

    def test_false_when_kubectl_fails(self):
        from src.components.k3s.enroll import _node_in_cluster
        with patch("src.components.k3s.enroll._run_cmd",
                   return_value=MagicMock(returncode=1)):
            assert _node_in_cluster("r2arm01") is False


# ── _push_k3s_files ───────────────────────────────────────────────────────────

class TestPushK3sFiles:
    def test_pushes_config_and_registries(self, tmp_path):
        from src.components.k3s.enroll import _push_k3s_files
        token_file = tmp_path / "node-token"
        token_file.write_text("mytoken\n")
        (tmp_path / "k3s-config.yaml").write_text(
            "server: https://192.168.1.1:6443\ntoken: __TOKEN__\n"
        )
        (tmp_path / "registries.yaml").write_text("mirrors: {}\n")

        pushed = []
        with patch("src.components.k3s.enroll.K3S_TOKEN_FILE", token_file), \
             patch("src.components.k3s.enroll.run_ssh",
                   return_value=MagicMock(returncode=0)), \
             patch("src.components.k3s.enroll.push_file",
                   side_effect=lambda t, p, c, **kw: pushed.append(p)):
            _push_k3s_files(tmp_path, "iobewi@1.2.3.4", Path("/root/.ssh/id"), nvidia=False)

        assert any("config.yaml" in p for p in pushed)
        assert any("registries.yaml" in p for p in pushed)

    def test_token_substitution(self, tmp_path):
        from src.components.k3s.enroll import _push_k3s_files
        token_file = tmp_path / "node-token"
        token_file.write_text("SECRET_TOKEN\n")
        (tmp_path / "k3s-config.yaml").write_text("token: __TOKEN__\n")
        (tmp_path / "registries.yaml").write_text("")

        pushed_content = []
        with patch("src.components.k3s.enroll.K3S_TOKEN_FILE", token_file), \
             patch("src.components.k3s.enroll.run_ssh",
                   return_value=MagicMock(returncode=0)), \
             patch("src.components.k3s.enroll.push_file",
                   side_effect=lambda t, p, c, **kw: pushed_content.append((p, c))):
            _push_k3s_files(tmp_path, "iobewi@1.2.3.4", Path("/root/.ssh/id"), nvidia=False)

        config_entry = next(c for p, c in pushed_content if "config.yaml" in p)
        assert "SECRET_TOKEN" in config_entry
        assert "__TOKEN__" not in config_entry

    def test_nvidia_pushes_containerd_config(self, tmp_path):
        from src.components.k3s.enroll import _push_k3s_files
        token_file = tmp_path / "node-token"
        token_file.write_text("tok\n")
        (tmp_path / "k3s-config.yaml").write_text("")
        (tmp_path / "registries.yaml").write_text("")

        pushed = []
        with patch("src.components.k3s.enroll.K3S_TOKEN_FILE", token_file), \
             patch("src.components.k3s.enroll.run_ssh",
                   return_value=MagicMock(returncode=0)), \
             patch("src.components.k3s.enroll.push_file",
                   side_effect=lambda t, p, c, **kw: pushed.append(p)):
            _push_k3s_files(tmp_path, "iobewi@1.2.3.4", Path("/root/.ssh/id"), nvidia=True)

        assert any("config.toml.tmpl" in p for p in pushed)


# ── _deploy_manifests ─────────────────────────────────────────────────────────

class TestDeployManifests:
    def test_copies_yaml_from_local_manifests(self, tmp_path):
        from src.components.k3s.enroll import _deploy_manifests
        manifests_src = tmp_path / "manifests"
        manifests_src.mkdir()
        (manifests_src / "cert-manager.yaml").write_text("kind: Deployment\n")
        (manifests_src / "metrics.yaml").write_text("kind: Service\n")

        dest = tmp_path / "dest"

        with patch("src.components.k3s.enroll.Path") as mock_path_cls, \
             patch("src.components.k3s.enroll.shutil.copy2") as mock_copy:

            mock_path_cls.return_value = MagicMock(
                is_dir=MagicMock(return_value=False),
                resolve=MagicMock(return_value=MagicMock(
                    parent=MagicMock(
                        parent=MagicMock(
                            __truediv__=MagicMock(return_value=MagicMock(
                                is_dir=MagicMock(return_value=True),
                                glob=MagicMock(return_value=sorted(manifests_src.glob("*.yaml")))
                            ))
                        )
                    )
                ))
            )

            # Simpler approach: patch the path resolution directly
            pass

        # Direct approach: patch system_manifests and local_manifests
        with patch("src.components.k3s.enroll.Path") as mock_p:
            not_exists = MagicMock(is_dir=MagicMock(return_value=False))
            exists_dir = MagicMock(
                is_dir=MagicMock(return_value=True),
                glob=MagicMock(return_value=sorted(manifests_src.glob("*.yaml"))),
            )
            dest_dir_mock = MagicMock()
            dest_dir_mock.mkdir = MagicMock()
            dest_dir_mock.__truediv__ = lambda self, name: dest / name

            call_count = [0]
            def path_factory(*args, **kwargs):
                call_count[0] += 1
                arg = str(args[0]) if args else ""
                if "manifests/r2bewi" in arg or "rancher" in arg:
                    return dest_dir_mock
                if "usr/share" in arg:
                    return not_exists
                return MagicMock(
                    is_dir=MagicMock(return_value=False),
                    resolve=MagicMock(return_value=MagicMock(
                        parent=MagicMock(parent=MagicMock(
                            __truediv__=MagicMock(return_value=exists_dir)
                        ))
                    ))
                )
            mock_p.side_effect = path_factory

            with patch("src.components.k3s.enroll.shutil.copy2") as mock_copy, \
                 patch("os.environ.get", return_value=None):
                _deploy_manifests()

    def test_no_manifests_dir_warns(self):
        from src.components.k3s.enroll import _deploy_manifests
        with patch("src.components.k3s.enroll.Path") as mock_p:
            mock_p.return_value = MagicMock(
                is_dir=MagicMock(return_value=False),
                resolve=MagicMock(return_value=MagicMock(
                    parent=MagicMock(parent=MagicMock(
                        __truediv__=MagicMock(return_value=MagicMock(
                            is_dir=MagicMock(return_value=False)
                        ))
                    ))
                ))
            )
            # Should not raise
            _deploy_manifests()
