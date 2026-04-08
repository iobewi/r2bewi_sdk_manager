"""
Tests unitaires — validateurs YAML dans src.core.validate

Couvre :
- _validate_node_profile (via validate.py + profile.py)
- _validate_k3s_config
- _validate_netplan
- _validate_sysctl
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
import yaml


# ── Helpers catalog ───────────────────────────────────────────────────────────

_CATALOG = {
    "compute": {
        "accelerator": {
            "values": [
                {"value": "none"},
                {"value": "nvidia"},
                {"value": "intel"},
            ]
        },
        "class": {
            "values": [
                {"value": "micro"},
                {"value": "embedded"},
                {"value": "general"},
                {"value": "high"},
            ]
        },
        "realtime": {
            "values": [
                {"value": "true"},
                {"value": "false"},
            ]
        },
    },
    "device": {},
}


def _write_yaml(path: Path, data: dict) -> None:
    path.write_text(yaml.dump(data))


# ── TestNodeProfileValidator ──────────────────────────────────────────────────

class TestNodeProfileValidator:
    """Tests pour _validate_node_profile via validate_profile() + load_catalog()."""

    def _validate(self, profile: dict) -> list[str]:
        from src.system.profile import validate_profile
        return validate_profile(profile, _CATALOG)

    def test_valid_profile_passes(self, tmp_path):
        profile = {
            "compute": {
                "accelerator": "none",
                "class": "embedded",
                "realtime": "false",
            }
        }
        errors = self._validate(profile)
        assert errors == []

    def test_missing_compute_fails(self, tmp_path):
        """Un profil sans compute génère des erreurs pour chaque champ obligatoire."""
        profile = {}
        errors = self._validate(profile)
        assert any("compute.accelerator" in e for e in errors)
        assert any("compute.class" in e for e in errors)
        assert any("compute.realtime" in e for e in errors)

    def test_missing_required_compute_field_fails(self, tmp_path):
        """compute.realtime manquant → erreur."""
        profile = {
            "compute": {
                "accelerator": "none",
                "class": "embedded",
                # realtime absent
            }
        }
        errors = self._validate(profile)
        assert any("compute.realtime" in e for e in errors)

    def test_invalid_accelerator_value_fails(self, tmp_path):
        """Valeur d'accélérateur inconnue → erreur."""
        profile = {
            "compute": {
                "accelerator": "tpu",  # not in catalog
                "class": "embedded",
                "realtime": "false",
            }
        }
        errors = self._validate(profile)
        assert any("accelerator" in e and "tpu" in e for e in errors)

    def test_invalid_class_value_fails(self, tmp_path):
        """Valeur de class inconnue → erreur."""
        profile = {
            "compute": {
                "accelerator": "none",
                "class": "supercomputer",  # not in catalog
                "realtime": "false",
            }
        }
        errors = self._validate(profile)
        assert any("class" in e and "supercomputer" in e for e in errors)

    def test_valid_profile_with_device_passes(self, tmp_path):
        """Profil avec device optionnel valide → OK."""
        catalog_with_device = {
            **_CATALOG,
            "device": {
                "camera": {
                    "values": [{"value": "mono"}, {"value": "stereo"}]
                }
            },
        }
        from src.system.profile import validate_profile
        profile = {
            "compute": {
                "accelerator": "none",
                "class": "embedded",
                "realtime": "false",
            },
            "device": {
                "camera": "mono",
            }
        }
        errors = validate_profile(profile, catalog_with_device)
        assert errors == []

    def test_via_file_with_catalog_mock(self, tmp_path):
        """Test via _validate_node_profile avec catalog mocké."""
        profile_path = tmp_path / "node-profile.yaml"
        _write_yaml(profile_path, {
            "compute": {
                "accelerator": "none",
                "class": "embedded",
                "realtime": "false",
            }
        })

        with patch("src.core.validate.load_catalog", return_value=_CATALOG), \
             patch("src.core.validate.validate_profile", return_value=[]):
            from src.core.validate import _validate_node_profile
            errors = _validate_node_profile(profile_path)

        assert errors == []


# ── TestK3sConfigValidator ────────────────────────────────────────────────────

class TestK3sConfigValidator:
    """Tests pour _validate_k3s_config."""

    def _make_dir(self, tmp_path, kind: str, content: dict) -> Path:
        node_dir = tmp_path / "node"
        node_dir.mkdir()
        (node_dir / "meta.yaml").write_text(f"kind: {kind}\n")
        config_path = node_dir / "k3s-config.yaml"
        _write_yaml(config_path, content)
        return config_path

    def test_valid_server_config_passes(self, tmp_path):
        config_path = self._make_dir(tmp_path, "server", {"node-label": []})
        from src.core.validate import _validate_k3s_config
        errors = _validate_k3s_config(config_path)
        assert errors == []

    def test_valid_agent_config_passes(self, tmp_path):
        config_path = self._make_dir(tmp_path, "agent", {
            "server": "https://192.168.1.1:6443",
            "token": "mytoken",
            "node-label": [],
        })
        from src.core.validate import _validate_k3s_config
        errors = _validate_k3s_config(config_path)
        assert errors == []

    def test_missing_server_field_fails(self, tmp_path):
        """Agent sans 'server' → erreur."""
        config_path = self._make_dir(tmp_path, "agent", {
            "token": "mytoken",
            "node-label": [],
        })
        from src.core.validate import _validate_k3s_config
        errors = _validate_k3s_config(config_path)
        assert any("server" in e for e in errors)

    def test_missing_token_fails(self, tmp_path):
        """Agent sans 'token' → erreur."""
        config_path = self._make_dir(tmp_path, "agent", {
            "server": "https://192.168.1.1:6443",
            "node-label": [],
        })
        from src.core.validate import _validate_k3s_config
        errors = _validate_k3s_config(config_path)
        assert any("token" in e for e in errors)

    def test_server_without_https_fails(self, tmp_path):
        """Agent avec server non-https → erreur."""
        config_path = self._make_dir(tmp_path, "agent", {
            "server": "http://192.168.1.1:6443",
            "token": "mytoken",
            "node-label": [],
        })
        from src.core.validate import _validate_k3s_config
        errors = _validate_k3s_config(config_path)
        assert any("https" in e for e in errors)

    def test_invalid_node_label_fails(self, tmp_path):
        """node-label avec entrée invalide (sans '=') → erreur."""
        config_path = self._make_dir(tmp_path, "server", {
            "node-label": ["invalid-without-equals"],
        })
        from src.core.validate import _validate_k3s_config
        errors = _validate_k3s_config(config_path)
        assert any("node-label" in e for e in errors)

    def test_node_label_not_list_fails(self, tmp_path):
        """node-label non-liste → erreur."""
        config_path = self._make_dir(tmp_path, "server", {
            "node-label": "single-string",
        })
        from src.core.validate import _validate_k3s_config
        errors = _validate_k3s_config(config_path)
        assert any("node-label" in e for e in errors)


# ── TestNetplanValidator ──────────────────────────────────────────────────────

class TestNetplanValidator:
    """Tests pour _validate_netplan."""

    def test_valid_netplan_passes(self, tmp_path):
        netplan_path = tmp_path / "netplan.yaml"
        _write_yaml(netplan_path, {
            "network": {
                "version": 2,
                "ethernets": {
                    "eth0": {"dhcp4": True}
                }
            }
        })
        from src.core.validate import _validate_netplan
        errors = _validate_netplan(netplan_path)
        assert errors == []

    def test_missing_network_key_fails(self, tmp_path):
        netplan_path = tmp_path / "netplan.yaml"
        _write_yaml(netplan_path, {"version": 2})
        from src.core.validate import _validate_netplan
        errors = _validate_netplan(netplan_path)
        assert any("network" in e for e in errors)

    def test_wrong_version_fails(self, tmp_path):
        netplan_path = tmp_path / "netplan.yaml"
        _write_yaml(netplan_path, {
            "network": {
                "version": 1,
                "ethernets": {"eth0": {"dhcp4": True}}
            }
        })
        from src.core.validate import _validate_netplan
        errors = _validate_netplan(netplan_path)
        assert any("version" in e for e in errors)

    def test_missing_version_fails(self, tmp_path):
        netplan_path = tmp_path / "netplan.yaml"
        _write_yaml(netplan_path, {
            "network": {
                "ethernets": {"eth0": {"dhcp4": True}}
            }
        })
        from src.core.validate import _validate_netplan
        errors = _validate_netplan(netplan_path)
        assert any("version" in e for e in errors)

    def test_no_interfaces_declared_fails(self, tmp_path):
        netplan_path = tmp_path / "netplan.yaml"
        _write_yaml(netplan_path, {
            "network": {
                "version": 2,
            }
        })
        from src.core.validate import _validate_netplan
        errors = _validate_netplan(netplan_path)
        assert any("interface" in e for e in errors)

    def test_network_not_dict_fails(self, tmp_path):
        netplan_path = tmp_path / "netplan.yaml"
        netplan_path.write_text("network: just-a-string\n")
        from src.core.validate import _validate_netplan
        errors = _validate_netplan(netplan_path)
        assert any("network" in e for e in errors)


# ── TestSysctlValidator ───────────────────────────────────────────────────────

class TestSysctlValidator:
    """Tests pour _validate_sysctl."""

    def test_valid_sysctl_passes(self, tmp_path):
        sysctl_path = tmp_path / "sysctl.conf"
        sysctl_path.write_text(
            "# sysctl config\n"
            "net.ipv4.ip_forward=1\n"
            "net.ipv6.conf.all.forwarding=1\n"
        )
        from src.core.validate import _validate_sysctl
        errors = _validate_sysctl(sysctl_path)
        assert errors == []

    def test_missing_ip_forward_passes(self, tmp_path):
        """_validate_sysctl ne vérifie pas la présence de ip_forward — juste le format."""
        sysctl_path = tmp_path / "sysctl.conf"
        sysctl_path.write_text("vm.swappiness=10\n")
        from src.core.validate import _validate_sysctl
        errors = _validate_sysctl(sysctl_path)
        assert errors == []

    def test_invalid_line_format_fails(self, tmp_path):
        """Ligne sans '=' → erreur de format."""
        sysctl_path = tmp_path / "sysctl.conf"
        sysctl_path.write_text("net.ipv4.ip_forward 1\n")  # space instead of =
        from src.core.validate import _validate_sysctl
        errors = _validate_sysctl(sysctl_path)
        assert len(errors) >= 1
        assert any("invalide" in e or "format" in e for e in errors)

    def test_comments_and_empty_lines_ignored(self, tmp_path):
        """Commentaires et lignes vides ne génèrent pas d'erreurs."""
        sysctl_path = tmp_path / "sysctl.conf"
        sysctl_path.write_text(
            "# This is a comment\n"
            "\n"
            "  # Another comment\n"
            "net.ipv4.ip_forward=1\n"
        )
        from src.core.validate import _validate_sysctl
        errors = _validate_sysctl(sysctl_path)
        assert errors == []

    def test_empty_file_passes(self, tmp_path):
        """Fichier vide ou uniquement commentaires → OK."""
        sysctl_path = tmp_path / "sysctl.conf"
        sysctl_path.write_text("# just a comment\n")
        from src.core.validate import _validate_sysctl
        errors = _validate_sysctl(sysctl_path)
        assert errors == []

    def test_multiple_invalid_lines_reported(self, tmp_path):
        """Plusieurs lignes invalides → plusieurs erreurs."""
        sysctl_path = tmp_path / "sysctl.conf"
        sysctl_path.write_text("invalid line one\ninvalid line two\n")
        from src.core.validate import _validate_sysctl
        errors = _validate_sysctl(sysctl_path)
        assert len(errors) == 2
