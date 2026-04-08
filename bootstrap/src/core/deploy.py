"""
role:
    Appliquer la configuration d'un nœud — localement ou à distance.

responsibilities:
    - définir le hostname, désactiver le swap
    - appliquer les fichiers système via les modules applicatifs
    - configurer NAT/IP forwarding (serveur)
    - installer registry et WireGuard (serveur local uniquement)

does_not:
    - installer K3s (géré par k3s/enroll.py)
    - gérer la pile applicative ROS 2 / Zenoh

review_focus:
    - dnsmasq.restore_resolved dans k3s/uninstall.py doit rester
      en sync avec dnsmasq.configure_resolved appelé ici
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from ..system.base import (
    NODES_DIR, error, get_kind, info, ok,
    push_file, resolve_ip, resolve_ssh_user, run, run_ssh,
    section, ssh_target, which,
)
from ..system.subprocess_utils import ssh_quote
from ..system.iobewi_setup import create_iobewi_on_agent, ensure_iobewi_key
from .validate import validate_node_dir
from ..components.registry import setup as _registry
from ..components.wireguard import server as _wireguard
from ..system.component import all_node_files as _all_node_files
from ..system.debian.packages import install_packages as _install_packages, agent_packages as _agent_packages


def register(sub) -> None:
    p = sub.add_parser("deploy",
                       help="Appliquer la config : local (sans --ip) ou distant via SSH (avec --ip)")
    p.add_argument("hostname", metavar="HOSTNAME")
    p.add_argument("--ip", metavar="ADDRESS", default=None,
                   help="IP de la cible (absent → application locale)")
    p.add_argument("--ssh-user", metavar="USER", default=None,
                   help="User SSH sur la cible (défaut : iobewi, ou valeur dans meta.yaml)")
    p.add_argument("--registry-size", metavar="SIZE", default="256G",
                   help="Taille du LV LVM pour le registry (ex. 128G, 1T — défaut : 256G)")


def run(args) -> None:
    node_dir = NODES_DIR / args.hostname
    if not node_dir.is_dir():
        error(f"Répertoire introuvable : {node_dir}")
        error(f"  Lancer d'abord : sudo r2bewi init {args.hostname} --kind <server|agent>")
        sys.exit(1)

    resolved_ip = resolve_ip(args.hostname, node_dir, args.ip)
    resolved_user = resolve_ssh_user(node_dir, args.ssh_user)

    if resolved_ip is None:
        _run_local(args.hostname, node_dir, args.registry_size)
    else:
        target = ssh_target(args.hostname, resolved_ip, resolved_user)
        _run_remote(args.hostname, node_dir, target)


# ── Local ─────────────────────────────────────────────────────────────────────

def _run_local(hostname: str, node_dir: Path, registry_size: str = "256G") -> None:
    _preflight_local(hostname, node_dir)
    _validate(node_dir)
    _set_hostname_local(hostname)
    _disable_swap_local()

    section("Paquets système")
    _install_packages(node_dir)

    section("Composants")
    _apply_components(node_dir)

    if get_kind(node_dir) == "server":
        section("Registry Docker locale")
        _registry.install(node_dir, registry_size)

        section("WireGuard serveur")
        _wireguard.setup(node_dir)

    ok(f"=== deploy {hostname} (local) terminé ===")
    print()
    print(f"Prochaine étape : sudo r2bewi enroll {hostname}")


def _preflight_local(hostname: str, node_dir: Path) -> None:
    section("Préflight")
    if os.geteuid() != 0:
        error("r2bewi deploy doit être exécuté en root (sudo)")
        sys.exit(1)
    missing = [t for t in ("hostnamectl", "netplan", "systemctl", "sysctl") if not which(t)]
    if missing:
        error(f"Outils requis introuvables : {', '.join(missing)}")
        error(f"  → sudo apt-get install -y {' '.join(missing)}")
        sys.exit(1)
    info(f"Nœud    : {hostname}")
    info(f"Sources : {node_dir}")
    ok("Préflight OK")


def _set_hostname_local(hostname: str) -> None:
    section("Hostname")
    info(f"hostname → {hostname}")
    run(["hostnamectl", "set-hostname", hostname])
    ok("Identité OK")


def _disable_swap_local() -> None:
    section("Swap")
    info("swapoff -a")
    run(["swapoff", "-a"], check=False)
    fstab = Path("/etc/fstab")
    if fstab.exists():
        lines = fstab.read_text().splitlines(keepends=True)
        kept = [l for l in lines if not _is_fstab_swap_entry(l)]
        removed = len(lines) - len(kept)
        if removed:
            fstab.write_text("".join(kept))
            info(f"/etc/fstab : {removed} ligne(s) swap supprimée(s)")
    ok("Swap désactivé")


def _apply_components(node_dir: Path) -> None:
    from ..system.component import load_all
    for comp in load_all():
        comp.call_setup(node_dir)


# ── Distant ───────────────────────────────────────────────────────────────────

def _run_remote(hostname: str, node_dir: Path, target: str) -> None:
    target, identity = _ensure_iobewi_identity(hostname, target)
    _validate(node_dir)
    _set_hostname_remote(target, hostname, identity)
    _update_system_remote(target, identity)
    _disable_swap_remote(target, identity)
    _push_node_files(hostname, node_dir, target, identity)
    _reboot_remote(target, hostname, identity)


def _ensure_iobewi_identity(hostname: str, target: str) -> tuple[str, Path]:
    """Garantit la clé iobewi et crée l'utilisateur si le bootstrap_user est différent."""
    ssh_user = target.split("@")[0]
    ip = target.split("@")[1]
    identity = ensure_iobewi_key()
    if ssh_user != "iobewi":
        section("Bootstrap iobewi")
        create_iobewi_on_agent(target, identity)
        target = ssh_target(hostname, ip, "iobewi")
        ok(f"Reconnexion avec iobewi sur {ip}")
    return target, identity


def _set_hostname_remote(target: str, hostname: str, identity: Path) -> None:
    section(f"Identité {hostname}")
    run_ssh(target, f"sudo hostnamectl set-hostname {ssh_quote(hostname)}", identity=identity)
    run_ssh(target, f"echo {ssh_quote(hostname)} | sudo tee /etc/hostname > /dev/null",
            identity=identity)
    run_ssh(target,
            f"if [ -f /boot/firmware/user-data ]; then "
            f"sudo sed -i 's|^hostname:.*|hostname: {hostname}|' /boot/firmware/user-data && "
            f"sudo sed -i 's|^manage_etc_hosts:.*|manage_etc_hosts: false|' /boot/firmware/user-data; "
            f"fi", identity=identity)
    run_ssh(target, "sudo mkdir -p /etc/cloud && sudo touch /etc/cloud/cloud-init.disabled",
            identity=identity)
    ok("Identité OK")


def _update_system_remote(target: str, identity: Path) -> None:
    section("Mise à jour système")
    info("apt-get update + upgrade (peut prendre quelques minutes)...")
    run_ssh(target,
            "sudo DEBIAN_FRONTEND=noninteractive apt-get update -qq"
            " && sudo DEBIAN_FRONTEND=noninteractive apt-get upgrade -y -qq"
            " && sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq"
            f" {' '.join(_agent_packages())}",
            identity=identity)
    ok("Système à jour, paquets installés")


def _disable_swap_remote(target: str, identity: Path) -> None:
    section("Swap")
    run_ssh(target, "sudo swapoff -a; sudo sed -i '/swap/d' /etc/fstab",
            check=False, identity=identity)
    ok("Swap désactivé")


def _push_node_files(hostname: str, node_dir: Path, target: str, identity: Path) -> None:
    section("Fichiers")
    kind = get_kind(node_dir)
    file_map = _all_node_files(kind)
    to_deploy = [(f, node_dir / f) for f in file_map if (node_dir / f).exists()]
    if not to_deploy:
        error(f"Aucun fichier à déployer dans {node_dir}")
        sys.exit(1)
    for filename, local_path in to_deploy:
        remote_path = file_map[filename]
        info(f"  {filename} → {target}:{remote_path}")
        run_ssh(target, f"sudo mkdir -p {ssh_quote(str(Path(remote_path).parent))}", identity=identity)
        push_file(target, remote_path, local_path.read_text(), identity=identity)
    ok(f"=== deploy {hostname} (distant) terminé ===")


def _reboot_remote(target: str, hostname: str, identity: Path | None = None) -> None:
    section("Reboot")
    info(f"Redémarrage de {hostname}...")
    run_ssh(target, "sudo reboot", check=False, identity=identity)
    ok("Reboot lancé — attendre que le nœud soit de nouveau joignable")
    print()
    print(f"Prochaine étape : sudo r2bewi enroll {hostname}")


# ── Partagé ───────────────────────────────────────────────────────────────────

def _validate(node_dir: Path) -> None:
    section("Validation")
    if not validate_node_dir(node_dir, kind=get_kind(node_dir)):
        error("Validation échouée — corriger les erreurs avant de déployer")
        sys.exit(1)
    ok("Validation OK")


def _is_fstab_swap_entry(line: str) -> bool:
    """Retourne True uniquement si la ligne est une entrée fstab active de type swap (colonne 3)."""
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return False
    fields = stripped.split()
    return len(fields) >= 3 and fields[2].lower() == "swap"
