"""
role:
    Appliquer la configuration réseau netplan.

responsibilities:
    - archiver les configs netplan existantes avant écrasement
    - désactiver la gestion réseau de cloud-init
    - appliquer netplan generate / apply

does_not:
    - gérer dnsmasq ou NAT
"""
from __future__ import annotations

from pathlib import Path

from ...system.base import _backup, info, ok, run, section, which


def deploy(node_dir: Path) -> None:
    section("netplan")
    apply(node_dir)


def apply(node_dir: Path) -> None:
    src = node_dir / "netplan.yaml"
    if not src.exists():
        info("netplan.yaml absent — ignoré")
        return
    content = src.read_text()
    dest = Path("/etc/netplan/50-r2bewi.yaml")
    if dest.exists() and dest.read_text() == content:
        info("netplan.yaml identique — ignoré")
        return
    for f in _backup.archive_directory("/etc/netplan/", "*.yaml"):
        info(f"  Archivé : {f}")
    _disable_cloud_init_network()
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(content)
    dest.chmod(0o600)
    info(f"  netplan.yaml → {dest}")
    run(["netplan", "generate"])
    if which("k3s"):
        info("  K3s déjà installé — netplan apply différé au prochain reboot")
        info("  (évite de couper la connexion SSH active)")
    else:
        run(["netplan", "apply"])
        ok("netplan appliqué")


def _disable_cloud_init_network() -> None:
    cfg_dir = Path("/etc/cloud/cloud.cfg.d")
    if not cfg_dir.exists():
        return
    marker = cfg_dir / "99-disable-network-config.cfg"
    if not marker.exists():
        marker.write_text("network: {config: disabled}\n")
        info("  cloud-init network désactivé")
