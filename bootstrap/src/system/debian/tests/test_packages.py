"""Tests unitaires — src.system.debian.packages"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


class TestAgentPackages:
    def test_returns_list(self):
        from src.system.debian.packages import agent_packages
        pkgs = agent_packages()
        assert isinstance(pkgs, list)

    def test_no_duplicates(self):
        from src.system.debian.packages import agent_packages
        pkgs = agent_packages()
        assert len(pkgs) == len(set(pkgs))

    def test_uses_agent_components(self):
        """Seuls les composants qui s'appliquent à agent sont inclus."""
        mock_comp_agent = MagicMock()
        mock_comp_agent.applies_to.return_value = True
        mock_comp_agent.packages = ["pkg-agent"]

        mock_comp_server = MagicMock()
        mock_comp_server.applies_to.return_value = False
        mock_comp_server.packages = ["pkg-server"]

        with patch("src.system.debian.packages.load_all",
                   return_value=[mock_comp_agent, mock_comp_server]):
            from src.system.debian.packages import agent_packages
            pkgs = agent_packages()

        assert "pkg-agent" in pkgs
        assert "pkg-server" not in pkgs


class TestInstallPackages:
    def test_runs_apt_update_upgrade_install(self, tmp_path):
        (tmp_path / "meta.yaml").write_text("kind: server\n")

        mock_comp = MagicMock()
        mock_comp.applies_to.return_value = True
        mock_comp.packages = ["curl", "jq"]

        run_calls = []

        def fake_run(cmd, **kwargs):
            run_calls.append(cmd)
            return MagicMock(returncode=0)

        with patch("src.system.debian.packages.load_all", return_value=[mock_comp]), \
             patch("src.system.debian.packages.get_kind", return_value="server"), \
             patch("src.system.subprocess_utils.run", side_effect=fake_run):
            from src.system.debian.packages import install_packages
            install_packages(tmp_path)

        cmds = [c[0] for c in run_calls]
        assert "apt-get" in cmds[0]
        assert "update" in run_calls[0]
        assert "upgrade" in run_calls[1]
        assert "install" in run_calls[2]
        assert "curl" in run_calls[2]
        assert "jq" in run_calls[2]

    def test_skips_install_when_no_packages(self, tmp_path):
        (tmp_path / "meta.yaml").write_text("kind: agent\n")

        mock_comp = MagicMock()
        mock_comp.applies_to.return_value = False
        mock_comp.packages = []

        run_calls = []

        def fake_run(cmd, **kwargs):
            run_calls.append(cmd)
            return MagicMock(returncode=0)

        with patch("src.system.debian.packages.load_all", return_value=[mock_comp]), \
             patch("src.system.debian.packages.get_kind", return_value="agent"), \
             patch("src.system.subprocess_utils.run", side_effect=fake_run):
            from src.system.debian.packages import install_packages
            install_packages(tmp_path)

        install_calls = [c for c in run_calls if "install" in c]
        assert install_calls == []

    def test_deduplicates_packages(self, tmp_path):
        mock_comp1 = MagicMock()
        mock_comp1.applies_to.return_value = True
        mock_comp1.packages = ["curl", "jq"]

        mock_comp2 = MagicMock()
        mock_comp2.applies_to.return_value = True
        mock_comp2.packages = ["jq", "wget"]

        install_cmd = []

        def fake_run(cmd, **kwargs):
            if "install" in cmd:
                install_cmd.extend(cmd)
            return MagicMock(returncode=0)

        with patch("src.system.debian.packages.load_all",
                   return_value=[mock_comp1, mock_comp2]), \
             patch("src.system.debian.packages.get_kind", return_value="server"), \
             patch("src.system.subprocess_utils.run", side_effect=fake_run):
            from src.system.debian.packages import install_packages
            install_packages(tmp_path)

        pkgs = [p for p in install_cmd if not p.startswith("-") and p != "apt-get" and p != "install"]
        assert len(pkgs) == len(set(pkgs)), f"Duplicates found: {pkgs}"
