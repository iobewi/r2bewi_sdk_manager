"""Tests unitaires — src.system.debian.services"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.system.debian.services import disable, enable, is_active, restart, start, stop


class TestEnable:
    def test_calls_systemctl_enable(self):
        with patch("src.system.debian.services.run") as mock_run:
            enable("docker-registry")
        mock_run.assert_called_once_with(["systemctl", "enable", "docker-registry"])

    def test_propagates_commanderror(self):
        from src.system.subprocess_utils import CommandError
        with patch("src.system.debian.services.run",
                   side_effect=CommandError(["systemctl"], 1, "failed")):
            with pytest.raises(CommandError):
                enable("unknown-svc")


class TestStart:
    def test_calls_systemctl_start(self):
        with patch("src.system.debian.services.run") as mock_run:
            start("k3s")
        mock_run.assert_called_once_with(["systemctl", "start", "k3s"])


class TestRestart:
    def test_calls_systemctl_restart(self):
        with patch("src.system.debian.services.run") as mock_run:
            restart("dnsmasq")
        mock_run.assert_called_once_with(["systemctl", "restart", "dnsmasq"])


class TestStop:
    def test_calls_systemctl_stop(self):
        with patch("src.system.debian.services.run") as mock_run:
            stop("wireguard")
        mock_run.assert_called_once_with(["systemctl", "stop", "wireguard"])


class TestDisable:
    def test_calls_systemctl_disable(self):
        with patch("src.system.debian.services.run") as mock_run:
            disable("docker-registry")
        mock_run.assert_called_once_with(["systemctl", "disable", "docker-registry"])


class TestIsActive:
    def test_returns_true_when_returncode_zero(self):
        with patch("src.system.debian.services.run",
                   return_value=MagicMock(returncode=0)):
            assert is_active("k3s") is True

    def test_returns_false_when_returncode_nonzero(self):
        with patch("src.system.debian.services.run",
                   return_value=MagicMock(returncode=3)):
            assert is_active("k3s") is False

    def test_calls_with_quiet_flag(self):
        with patch("src.system.debian.services.run",
                   return_value=MagicMock(returncode=0)) as mock_run:
            is_active("dnsmasq")
        args = mock_run.call_args[0][0]
        assert "--quiet" in args
        assert "is-active" in args
        assert "dnsmasq" in args
