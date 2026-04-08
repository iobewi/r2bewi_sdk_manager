"""Tests unitaires — src.system.state"""
from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.system.state import (
    _which,
    bridge_address,
    file_present,
    k3s_installed,
    k3s_token_present,
    node_ready,
    remote_service_active,
    service_active,
    ssh_key_present,
    ssh_reachable,
    sysctl_get,
)


class TestServiceActive:
    def test_returns_true_on_zero(self):
        with patch("src.system.state.subprocess.run",
                   return_value=MagicMock(returncode=0)):
            assert service_active("k3s") is True

    def test_returns_false_on_nonzero(self):
        with patch("src.system.state.subprocess.run",
                   return_value=MagicMock(returncode=3)):
            assert service_active("k3s") is False


class TestK3sInstalled:
    def test_true_when_k3s_in_path(self, tmp_path):
        fake_bin = tmp_path / "k3s"
        fake_bin.write_text("")
        with patch.dict(os.environ, {"PATH": str(tmp_path)}):
            assert k3s_installed() is True

    def test_false_when_k3s_absent(self, tmp_path):
        with patch.dict(os.environ, {"PATH": str(tmp_path)}):
            assert k3s_installed() is False


class TestK3sTokenPresent:
    def test_true_when_file_exists(self, tmp_path):
        token = tmp_path / "node-token"
        token.write_text("secret")
        with patch("src.system.state.Path", return_value=token):
            assert k3s_token_present() is True

    def test_false_when_file_absent(self, tmp_path):
        absent = tmp_path / "node-token"
        with patch("src.system.state.Path", return_value=absent):
            assert k3s_token_present() is False


class TestNodeReady:
    def test_ready(self):
        with patch("src.system.state.subprocess.run",
                   return_value=MagicMock(returncode=0, stdout="r2arm01  Ready  <none>")):
            ready, line = node_ready("r2arm01")
        assert ready is True
        assert "Ready" in line

    def test_not_ready(self):
        with patch("src.system.state.subprocess.run",
                   return_value=MagicMock(returncode=0, stdout="r2arm01  NotReady  <none>")):
            ready, line = node_ready("r2arm01")
        assert ready is False

    def test_kubectl_error(self):
        with patch("src.system.state.subprocess.run",
                   return_value=MagicMock(returncode=1, stdout="")):
            ready, line = node_ready("r2arm01")
        assert ready is False
        assert line == ""


class TestBridgeAddress:
    def test_returns_cidr(self):
        output = "2: br0    inet 192.168.82.1/24 brd 192.168.82.255 scope global br0\n"
        with patch("src.system.state.subprocess.run",
                   return_value=MagicMock(returncode=0, stdout=output)):
            assert bridge_address("br0") == "192.168.82.1/24"

    def test_returns_none_on_error(self):
        with patch("src.system.state.subprocess.run",
                   return_value=MagicMock(returncode=1, stdout="")):
            assert bridge_address("br0") is None

    def test_returns_none_when_no_inet(self):
        with patch("src.system.state.subprocess.run",
                   return_value=MagicMock(returncode=0, stdout="2: br0\n")):
            assert bridge_address("br0") is None

    def test_returns_none_on_empty_output(self):
        with patch("src.system.state.subprocess.run",
                   return_value=MagicMock(returncode=0, stdout="")):
            assert bridge_address("br0") is None


class TestSysctlGet:
    def test_returns_value(self):
        with patch("src.system.state.subprocess.run",
                   return_value=MagicMock(returncode=0, stdout="1\n")):
            assert sysctl_get("net.ipv4.ip_forward") == "1"

    def test_returns_none_on_error(self):
        with patch("src.system.state.subprocess.run",
                   return_value=MagicMock(returncode=1, stdout="")):
            assert sysctl_get("net.ipv4.ip_forward") is None


class TestSshKeyPresent:
    def test_true_when_key_exists(self, tmp_path):
        key = tmp_path / "id_ed25519"
        key.write_text("KEY")
        assert ssh_key_present(str(key)) is True

    def test_false_when_absent(self, tmp_path):
        assert ssh_key_present(str(tmp_path / "id_ed25519")) is False


class TestFilePresent:
    def test_true_when_file_exists(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("x")
        assert file_present(str(f)) is True

    def test_false_when_absent(self, tmp_path):
        assert file_present(str(tmp_path / "absent.txt")) is False


class TestSshReachable:
    def test_reachable(self):
        with patch("src.system.state.subprocess.run",
                   return_value=MagicMock(returncode=0, stdout="ok\n")):
            assert ssh_reachable("iobewi@192.168.82.10") is True

    def test_unreachable_nonzero(self):
        with patch("src.system.state.subprocess.run",
                   return_value=MagicMock(returncode=255, stdout="")):
            assert ssh_reachable("iobewi@192.168.82.10") is False

    def test_unreachable_bad_stdout(self):
        with patch("src.system.state.subprocess.run",
                   return_value=MagicMock(returncode=0, stdout="Permission denied")):
            assert ssh_reachable("iobewi@192.168.82.10") is False


class TestRemoteServiceActive:
    def test_active(self):
        with patch("src.system.state.subprocess.run",
                   return_value=MagicMock(returncode=0)):
            assert remote_service_active("iobewi@192.168.82.10", "k3s-agent") is True

    def test_inactive(self):
        with patch("src.system.state.subprocess.run",
                   return_value=MagicMock(returncode=3)):
            assert remote_service_active("iobewi@192.168.82.10", "k3s-agent") is False


class TestWhich:
    def test_finds_executable(self, tmp_path):
        bin_file = tmp_path / "mycmd"
        bin_file.write_text("")
        with patch.dict(os.environ, {"PATH": str(tmp_path)}):
            assert _which("mycmd") is True

    def test_returns_false_when_absent(self, tmp_path):
        with patch.dict(os.environ, {"PATH": str(tmp_path)}):
            assert _which("mycmd") is False

    def test_empty_path_components_skipped(self):
        with patch.dict(os.environ, {"PATH": ""}):
            assert _which("ls") is False
