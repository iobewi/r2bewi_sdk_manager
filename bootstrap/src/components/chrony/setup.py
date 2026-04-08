"""
role:
    Appliquer la configuration chrony (synchronisation NTP).

responsibilities:
    - copier chrony.conf vers /etc/chrony/chrony.conf
    - activer et redémarrer le service chrony

does_not:
    - installer chrony (géré par le paquet .deb)
"""
from __future__ import annotations

from pathlib import Path

from ...system.base import _svc, info, ok, section


def deploy(node_dir: Path) -> None:
    section("chrony")
    apply(node_dir)


def apply(node_dir: Path) -> None:
    src = node_dir / "chrony.conf"
    if not src.exists():
        info("chrony.conf absent — ignoré")
        return
    content = src.read_text()
    dest = Path("/etc/chrony/chrony.conf")
    if dest.exists() and dest.read_text() == content:
        info("chrony.conf identique — ignoré")
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(content)
    info(f"  chrony.conf → {dest}")
    _svc.enable("chrony")
    _svc.restart("chrony")
    ok("chrony appliqué")
