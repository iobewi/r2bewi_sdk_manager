"""
role:
    Gestion des paquets système — implémentation Debian/Ubuntu (apt).
"""
from __future__ import annotations
from pathlib import Path
from ..helpers import get_kind
from ..component import load_all


def agent_packages() -> list[str]:
    """Packages déclarés pour kind=agent dans tous les composants."""
    pkgs: list[str] = []
    for comp in load_all():
        if comp.applies_to("agent"):
            pkgs.extend(p for p in comp.packages if p not in pkgs)
    return pkgs


def install_packages(node_dir: Path) -> None:
    """Update + upgrade + install des paquets composants pour le kind du nœud."""
    from ..log import info, ok
    from ..subprocess_utils import run
    kind = get_kind(node_dir)
    pkgs: list[str] = []
    for comp in load_all():
        if comp.applies_to(kind):
            pkgs.extend(p for p in comp.packages if p not in pkgs)
    info("apt-get update...")
    run(["apt-get", "update", "-qq"])
    info("apt-get upgrade...")
    run(["apt-get", "upgrade", "-y", "-qq"])
    if not pkgs:
        ok("Système à jour — aucun paquet additionnel")
        return
    info(f"apt-get install : {' '.join(pkgs)}")
    run(["apt-get", "install", "-y", "-qq"] + pkgs)
    ok("Paquets installés")
