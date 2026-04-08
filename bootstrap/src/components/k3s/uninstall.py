"""
role:
    Désinstaller K3s et restaurer les fichiers gérés.

responsibilities:
    server : k3s-uninstall.sh, suppression fichiers gérés, restauration systemd-resolved
    agent  : k3s-agent-uninstall.sh distant, suppression fichiers distants, retrait du cluster

does_not:
    - désinstaller les paquets système installés par le .deb
    - restaurer la config réseau (netplan) ou dnsmasq
"""
from __future__ import annotations

import sys
from pathlib import Path

from ...system.base import (
    NODES_DIR, error, get_kind, info, ok,
    resolve_ip, resolve_ssh_user, run as _run_cmd, run_ssh, section, ssh_target, warn,
)
from ...system.subprocess_utils import ssh_quote
from ...system import backup as _backup
from ...system import state as _state
from ...system.component import all_managed_paths
from ..dnsmasq.setup import restore_resolved


def register(sub) -> None:
    p = sub.add_parser("uninstall", help="Désinstaller K3s et restaurer les fichiers gérés")
    p.add_argument("hostname", metavar="HOSTNAME")
    p.add_argument("--ip", metavar="ADDRESS", default=None)
    p.add_argument("--ssh-user", metavar="USER", default="iobewi")


_K3S_UNINSTALL = "/usr/local/bin/k3s-uninstall.sh"
_K3S_AGENT_UNINSTALL = "/usr/local/bin/k3s-agent-uninstall.sh"


def run(args) -> None:
    node_dir = NODES_DIR / args.hostname
    if not node_dir.is_dir():
        error(f"Répertoire introuvable : {node_dir}")
        error(f"  Lancer d'abord : sudo r2bewi init {args.hostname} --kind <server|agent>")
        sys.exit(1)

    kind = get_kind(node_dir)
    resolved_ip = resolve_ip(args.hostname, node_dir, args.ip)

    if kind == "server":
        _uninstall_server()
    else:
        effective_user = resolve_ssh_user(node_dir, args.ssh_user)
        target = ssh_target(args.hostname, resolved_ip, effective_user)
        _uninstall_agent(args.hostname, target)


def _uninstall_server() -> None:
    section("Désinstallation K3s server")
    if Path(_K3S_UNINSTALL).exists():
        info("Exécution k3s-uninstall.sh")
        _run_cmd(["bash", _K3S_UNINSTALL], check=False)
        ok("K3s server désinstallé")
    elif _state.k3s_installed():
        warn("k3s-uninstall.sh introuvable — K3s non désinstallé")
    else:
        info("K3s non installé — rien à faire")

    section("Suppression fichiers gérés")
    _remove_managed_files(all_managed_paths("server"))

    section("Restauration systemd-resolved")
    restore_resolved()

    ok("=== uninstall server terminé ===")


def _uninstall_agent(hostname: str, target: str) -> None:
    section("Désinstallation K3s agent")
    reachable = _state.ssh_reachable(target)
    if not reachable:
        warn(f"Cible SSH {target} inaccessible — désinstallation distante ignorée")
    else:
        result = run_ssh(
            target,
            f"[ -f {_K3S_AGENT_UNINSTALL} ] && sudo bash {_K3S_AGENT_UNINSTALL} || echo absent",
            check=False,
            capture=True,
        )
        if result.returncode == 0 and "absent" not in (result.stdout or ""):
            ok(f"K3s agent désinstallé sur {target}")
        else:
            info("k3s-agent-uninstall.sh absent ou K3s déjà désinstallé")

    section("Suppression fichiers distants")
    if reachable:
        for path in sorted(all_managed_paths("agent")):
            run_ssh(target, f"sudo rm -f {ssh_quote(path)}", check=False)
            info(f"  {path}")
    else:
        warn("Fichiers distants non supprimés (cible inaccessible)")

    section("Retrait du nœud du cluster")
    if _state.k3s_installed():
        _run_cmd(
            ["k3s", "kubectl", "delete", "node", hostname, "--ignore-not-found"],
            check=False,
        )
        info(f"Nœud {hostname!r} retiré du cluster")
    else:
        info("K3s non installé sur le bastion — retrait ignoré")

    ok(f"=== uninstall agent terminé : {hostname} ===")


def _remove_managed_files(paths: frozenset[str]) -> None:
    for path in sorted(paths):
        p = Path(path)
        if not p.exists():
            info(f"  Absent : {path}")
            continue
        if _backup.restore_file(path):
            ok(f"  Restauré depuis sauvegarde : {path}")
        else:
            p.unlink()
            info(f"  Supprimé : {path}")
