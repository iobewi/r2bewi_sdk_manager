"""
Tests — système de sauvegarde (backup.py)
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.system.backup import BACKUP_ROOT, archive_directory, backup_file, list_backups, restore_file


@pytest.fixture(autouse=True)
def isolated_backup(tmp_path, monkeypatch):
    """Redirige BACKUP_ROOT et _MANIFEST vers tmp_path pour l'isolation des tests."""
    import src.system.backup as _bk
    fake_root = tmp_path / "backup"
    monkeypatch.setattr(_bk, "BACKUP_ROOT", fake_root)
    monkeypatch.setattr(_bk, "_MANIFEST", fake_root / "manifest.json")


class TestBackupFile:
    def test_returns_none_if_file_absent(self, tmp_path):
        result = backup_file(tmp_path / "nonexistent.txt")
        assert result is None

    def test_copies_existing_file(self, tmp_path):
        src = tmp_path / "myfile.txt"
        src.write_text("original content")
        dst = backup_file(str(src))
        assert dst is not None
        assert dst.exists()
        assert dst.read_text() == "original content"

    def test_backup_path_contains_timestamp(self, tmp_path):
        src = tmp_path / "myfile.txt"
        src.write_text("x")
        dst = backup_file(str(src))
        # filename ends with .<YYYYMMDD-HHMMSS>
        import re
        assert re.search(r"\.\d{8}-\d{6}$", str(dst))

    def test_records_in_manifest(self, tmp_path):
        src = tmp_path / "myfile.txt"
        src.write_text("x")
        backup_file(str(src))
        backups = list_backups()
        assert str(src) in backups
        assert len(backups[str(src)]) == 1

    def test_multiple_backups_accumulated(self, tmp_path):
        src = tmp_path / "myfile.txt"
        src.write_text("v1")
        backup_file(str(src))
        src.write_text("v2")
        backup_file(str(src))
        backups = list_backups()
        assert len(backups[str(src)]) == 2


class TestRestoreFile:
    def test_returns_false_if_no_backup(self, tmp_path):
        assert restore_file(tmp_path / "ghost.txt") is False

    def test_restores_most_recent(self, tmp_path):
        src = tmp_path / "myfile.txt"
        src.write_text("v1")
        backup_file(str(src))
        src.write_text("v2")
        backup_file(str(src))
        src.write_text("v3 — current")

        restored = restore_file(str(src))
        assert restored is True
        # should restore v2 (most recent backup)
        assert src.read_text() == "v2"


class TestArchiveDirectory:
    def test_archives_matching_files(self, tmp_path):
        d = tmp_path / "conf.d"
        d.mkdir()
        (d / "a.conf").write_text("a")
        (d / "b.conf").write_text("b")
        (d / "keep.txt").write_text("keep")

        archived = archive_directory(str(d), "*.conf")

        assert len(archived) == 2
        # fichiers supprimés
        assert not (d / "a.conf").exists()
        assert not (d / "b.conf").exists()
        # fichier hors pattern conservé
        assert (d / "keep.txt").exists()

    def test_archived_files_in_backup(self, tmp_path):
        d = tmp_path / "conf.d"
        d.mkdir()
        (d / "a.conf").write_text("a")
        archive_directory(str(d), "*.conf")
        backups = list_backups()
        assert str(d / "a.conf") in backups

    def test_returns_empty_if_no_match(self, tmp_path):
        d = tmp_path / "conf.d"
        d.mkdir()
        (d / "file.txt").write_text("x")
        result = archive_directory(str(d), "*.conf")
        assert result == []

    def test_returns_empty_if_directory_absent(self, tmp_path):
        result = archive_directory(tmp_path / "nonexistent", "*.conf")
        assert result == []


class TestListBackups:
    def test_empty_if_no_manifest(self):
        assert list_backups() == {}

    def test_returns_dict(self, tmp_path):
        src = tmp_path / "myfile.txt"
        src.write_text("x")
        backup_file(str(src))
        result = list_backups()
        assert isinstance(result, dict)
        assert str(src) in result
