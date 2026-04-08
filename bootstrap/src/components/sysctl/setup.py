"""
role:
    Appliquer les paramètres noyau (sysctl).

responsibilities:
    - copier sysctl.conf vers /etc/sysctl.d/99-r2bewi.conf
    - recharger les paramètres via sysctl --system

does_not:
    - modifier d'autres fichiers système
"""
from __future__ import annotations

from pathlib import Path

from ...system.base import info, ok, run, section


def deploy(node_dir: Path) -> None:
    section("sysctl")
    apply(node_dir)


def apply(node_dir: Path) -> None:
    src = node_dir / "sysctl.conf"
    if not src.exists():
        info("sysctl.conf absent — ignoré")
        return
    content = src.read_text()
    dest = Path("/etc/sysctl.d/99-r2bewi.conf")
    if dest.exists() and dest.read_text() == content:
        info("sysctl.conf identique — ignoré")
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(content)
    info(f"  sysctl.conf → {dest}")
    run(["sysctl", "--system"])
    ok("sysctl appliqué")
