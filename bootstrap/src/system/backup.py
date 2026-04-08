"""
role:
    File backup and restore mechanism protecting system files modified by r2bewi.

responsibilities:
    - copy existing files to a timestamped backup before any overwrite
    - maintain a manifest.json index of all backup versions
    - restore the most recent backup on uninstall
    - bulk-archive a config directory before taking ownership of it

does_not:
    - back up files written by r2bewi itself (only pre-existing originals)
    - encrypt or compress backups

managed_files:
    - /var/lib/r2bewi/backup/manifest.json  (backup index)
    - /var/lib/r2bewi/backup/**/*            (backup copies)

side_effects:
    - backup_file(): writes to /var/lib/r2bewi/backup/ and updates manifest
    - restore_file(): overwrites the target path with the saved content
    - archive_directory(): removes the original files after backing them up

idempotency:
    - backup_file(): calling twice appends a second timestamped version;
      the original is not re-saved if it no longer exists
    - restore_file(): always restores the lexicographically latest backup

review_focus:
    - archive_directory() deletes the originals — only call when taking
      full ownership of a config directory (netplan, dnsmasq.d)
    - manifest.json is updated atomically per call but not transactionally;
      a crash mid-write could leave it inconsistent
"""
from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path

BACKUP_ROOT = Path("/var/lib/r2bewi/backup")
_MANIFEST = BACKUP_ROOT / "manifest.json"


def backup_file(path: str | Path) -> Path | None:
    """
    purpose:
        Copy an existing system file to a timestamped backup before overwrite.

    post:
        - backup stored under BACKUP_ROOT with relative path + timestamp suffix
        - manifest.json updated with original → backup mapping
        - returns backup path, or None if source file did not exist

    side_effects:
        - writes to /var/lib/r2bewi/backup/
        - updates manifest.json
    """
    src = Path(path)
    if not src.exists():
        return None

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    rel = str(src).lstrip("/")
    dst = BACKUP_ROOT / f"{rel}.{timestamp}"
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)

    _record(str(src), str(dst))
    return dst


def restore_file(path: str | Path) -> bool:
    """
    Restaure la sauvegarde la plus récente d'un fichier.
    Retourne True si restauré, False si aucune sauvegarde disponible.
    """
    backups = list_backups().get(str(Path(path)), [])
    if not backups:
        return False
    shutil.copy2(sorted(backups)[-1], path)
    return True


def list_backups() -> dict[str, list[str]]:
    """Retourne original_path → liste de chemins de sauvegarde (ordre chronologique)."""
    if not _MANIFEST.exists():
        return {}
    try:
        data = json.loads(_MANIFEST.read_text())
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def archive_directory(directory: str | Path, pattern: str = "*") -> list[Path]:
    """
    purpose:
        Back up and remove all matching files in a directory to take ownership.

    pre:
        - caller intends to replace all files in the directory with r2bewi-managed ones

    post:
        - all matched files are backed up and deleted from the source directory
        - returns the list of source paths that were archived and removed

    side_effects:
        - deletes original files from the directory
        - writes backups under BACKUP_ROOT

    review_focus:
        - destructive: originals are removed after backup; do not call unless
          r2bewi is taking full ownership of the directory
    """
    d = Path(directory)
    if not d.is_dir():
        return []

    archived = []
    for src in sorted(d.glob(pattern)):
        if src.is_file():
            dst = backup_file(src)
            if dst:
                archived.append(src)
                src.unlink()
    return archived


def _record(original: str, backup_path: str) -> None:
    manifest = list_backups()
    manifest.setdefault(original, []).append(backup_path)
    BACKUP_ROOT.mkdir(parents=True, exist_ok=True)
    _MANIFEST.write_text(json.dumps(manifest, indent=2))
