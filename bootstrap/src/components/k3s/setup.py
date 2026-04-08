"""
role:
    Déployer les fichiers de configuration K3s.

responsibilities:
    - copier k3s-config.yaml et registries.yaml vers /etc/rancher/k3s/

does_not:
    - installer K3s (géré par enroll.py)
    - configurer le cluster (géré par enroll.py)
"""
from __future__ import annotations

from pathlib import Path

from ...system.base import info, section

_FILES: dict[str, str] = {
    "k3s-config.yaml": "/etc/rancher/k3s/config.yaml",
    "registries.yaml": "/etc/rancher/k3s/registries.yaml",
}


def deploy(node_dir: Path) -> None:
    section("K3s config")
    for filename, dest_path in _FILES.items():
        src = node_dir / filename
        if not src.exists():
            info(f"  {filename} absent — ignoré")
            continue
        content = src.read_text()
        dest = Path(dest_path)
        if dest.exists() and dest.read_text() == content:
            info(f"  {filename} identique — ignoré")
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content)
        info(f"  {filename} → {dest_path}")
