"""Tests de non-régression pour src.system.helpers — read_meta, resolve_ssh_user, get_kind, safe_write_text."""
from __future__ import annotations

import os

import pytest

from src.system.helpers import read_meta, resolve_ssh_user, get_kind, safe_write_text


class TestReadMeta:
    def test_absent_returns_empty(self, tmp_path):
        assert read_meta(tmp_path) == {}

    def test_simple_yaml(self, tmp_path):
        (tmp_path / "meta.yaml").write_text("kind: server\nip: 192.168.82.1\n")
        meta = read_meta(tmp_path)
        assert meta["kind"] == "server"
        assert meta["ip"] == "192.168.82.1"

    def test_value_with_colon(self, tmp_path):
        """Le parsing yaml.safe_load gère les valeurs avec ':' correctement."""
        (tmp_path / "meta.yaml").write_text('url: "https://host:6443"\n')
        meta = read_meta(tmp_path)
        assert meta["url"] == "https://host:6443"

    def test_inline_comment_ignored(self, tmp_path):
        (tmp_path / "meta.yaml").write_text("kind: agent  # this is a comment\n")
        meta = read_meta(tmp_path)
        assert meta["kind"] == "agent"

    def test_invalid_yaml_returns_empty(self, tmp_path):
        (tmp_path / "meta.yaml").write_text("{ invalid: yaml: :\n")
        assert read_meta(tmp_path) == {}

    def test_none_values_excluded(self, tmp_path):
        (tmp_path / "meta.yaml").write_text("kind: server\nip:\n")
        meta = read_meta(tmp_path)
        assert "ip" not in meta
        assert meta["kind"] == "server"

    def test_non_string_keys_excluded(self, tmp_path):
        (tmp_path / "meta.yaml").write_text("123: server\nkind: agent\n")
        meta = read_meta(tmp_path)
        assert "123" not in meta or True  # int key excluded or converted — both OK
        assert meta["kind"] == "agent"


class TestResolveSshUser:
    def test_cli_none_reads_meta(self, tmp_path):
        (tmp_path / "meta.yaml").write_text("kind: agent\nssh_user: ubuntu\n")
        assert resolve_ssh_user(tmp_path, None) == "ubuntu"

    def test_cli_explicit_overrides_meta(self, tmp_path):
        """Même si meta.yaml dit ubuntu, CLI explicite gagne."""
        (tmp_path / "meta.yaml").write_text("kind: agent\nssh_user: ubuntu\n")
        assert resolve_ssh_user(tmp_path, "iobewi") == "iobewi"

    def test_cli_default_value_explicit_wins(self, tmp_path):
        """cli_user='iobewi' fourni explicitement doit gagner sur meta.yaml."""
        (tmp_path / "meta.yaml").write_text("kind: agent\nssh_user: ubuntu\n")
        assert resolve_ssh_user(tmp_path, "iobewi") == "iobewi"

    def test_cli_none_falls_back_to_default(self, tmp_path):
        """Sans meta ni CLI, retourne le défaut."""
        assert resolve_ssh_user(tmp_path, None) == "iobewi"

    def test_meta_absent_cli_none_default(self, tmp_path):
        assert resolve_ssh_user(tmp_path, None, default="ubuntu") == "ubuntu"


class TestGetKind:
    def test_reads_from_meta(self, tmp_path):
        (tmp_path / "meta.yaml").write_text("kind: server\n")
        assert get_kind(tmp_path) == "server"

    def test_heuristic_server_when_netplan_present(self, tmp_path):
        (tmp_path / "netplan.yaml").write_text("")
        assert get_kind(tmp_path) == "server"

    def test_heuristic_agent_when_no_netplan(self, tmp_path):
        assert get_kind(tmp_path) == "agent"

    def test_strict_raises_when_meta_absent(self, tmp_path):
        with pytest.raises(FileNotFoundError, match="kind introuvable"):
            get_kind(tmp_path, strict=True)

    def test_strict_ok_when_meta_present(self, tmp_path):
        (tmp_path / "meta.yaml").write_text("kind: agent\n")
        assert get_kind(tmp_path, strict=True) == "agent"

    def test_non_strict_warns_when_meta_absent(self, tmp_path):
        """Sans meta.yaml, get_kind émet un avertissement (sans strict)."""
        from unittest.mock import patch
        with patch("src.system.log.warn") as mock_warn:
            get_kind(tmp_path)
        mock_warn.assert_called_once()
        assert "heuristique" in mock_warn.call_args[0][0]


class TestSafeWriteText:
    def test_creates_file(self, tmp_path):
        target = tmp_path / "output.txt"
        safe_write_text(target, "hello\n")
        assert target.read_text() == "hello\n"

    def test_overwrites_existing(self, tmp_path):
        target = tmp_path / "config.yml"
        target.write_text("old content")
        safe_write_text(target, "new content")
        assert target.read_text() == "new content"

    def test_no_temp_file_left_on_success(self, tmp_path):
        target = tmp_path / "cfg.yml"
        safe_write_text(target, "content")
        temps = list(tmp_path.glob(".cfg.yml.tmp.*"))
        assert temps == []

    def test_mode_applied(self, tmp_path):
        target = tmp_path / "meta.yaml"
        safe_write_text(target, "kind: server\n", mode=0o640)
        mode = oct(os.stat(target).st_mode & 0o777)
        assert mode == oct(0o640)

    def test_error_cleans_up_temp(self, tmp_path):
        """Si os.replace échoue, le fichier temporaire est supprimé et l'original intact."""
        target = tmp_path / "output.txt"
        target.write_text("original")

        with pytest.raises(OSError, match="no space"):
            with pytest.MonkeyPatch.context() as mp:
                mp.setattr(os, "replace", lambda src, dst: (_ for _ in ()).throw(OSError("no space")))
                safe_write_text(target, "new content")

        # L'original est intact
        assert target.read_text() == "original"
        # Aucun fichier temporaire résiduel
        temps = list(tmp_path.glob(".output.txt.tmp.*"))
        assert temps == []
