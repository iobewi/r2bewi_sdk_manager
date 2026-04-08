"""
role:
    Inspection non-destructive de l'état courant du nœud.

does_not:
    - modifier l'état du système
    - vérifier les fichiers distants (marqués non vérifiables)
"""
from __future__ import annotations

import sys
from pathlib import Path

from ..system.base import NODES_DIR, error, get_kind, resolve_ip, resolve_ssh_user, ssh_target
from ..system import backup as _backup
from ..system import state as _state
from ..system.component import all_managed_paths


def register(sub) -> None:
    p = sub.add_parser("status", help="Afficher l'état du nœud")
    p.add_argument("hostname", metavar="HOSTNAME")
    p.add_argument("--ip", metavar="ADDRESS", default=None)
    p.add_argument("--ssh-user", metavar="USER", default="iobewi")


def run(args) -> None:
    node_dir = NODES_DIR / args.hostname
    if not node_dir.is_dir():
        error(f"Répertoire introuvable : {node_dir}")
        error(f"  Lancer d'abord : sudo r2bewi init {args.hostname} --kind <server|agent>")
        sys.exit(1)

    kind = get_kind(node_dir)
    resolved_ip = resolve_ip(args.hostname, node_dir, args.ip)
    print(f"\n=== Status : {args.hostname} ({kind}) ===")

    if kind == "server":
        _status_server(args.hostname, node_dir)
    else:
        effective_user = resolve_ssh_user(node_dir, args.ssh_user)
        target = ssh_target(args.hostname, resolved_ip, effective_user)
        _status_agent(args.hostname, target)

    _status_backups()
    print()


def _status_server(hostname: str, node_dir: Path) -> None:
    bridge_name = _read_bridge_name(node_dir)

    print()
    print("  Réseau")
    addr = _state.bridge_address(bridge_name)
    _row(bridge_name, addr or "absent", ok=addr is not None)
    fwd = _state.sysctl_get("net.ipv4.ip_forward")
    _row("ip_forward", fwd or "—", ok=fwd == "1")
    _row("dnsmasq", _svc_label("dnsmasq"), ok=_state.service_active("dnsmasq"))
    _row("avahi-daemon", _svc_label("avahi-daemon"), ok=_state.service_active("avahi-daemon"))

    print()
    print("  K3s server")
    installed = _state.k3s_installed()
    _row("k3s installé", "oui" if installed else "non", ok=installed)
    active = _state.service_active("k3s")
    _row("service k3s", _svc_label("k3s"), ok=active)
    token = _state.k3s_token_present()
    _row("token", "présent" if token else "absent", ok=token)
    if installed:
        ready, line = _state.node_ready(hostname)
        status_word = line.split()[1] if len(line.split()) > 1 else "—"
        _row(f"node {hostname}", status_word, ok=ready)

    print()
    print("  SSH")
    key = _state.ssh_key_present("/home/iobewi/.ssh/id_ed25519")
    _row("/home/iobewi/.ssh/id_ed25519", "présente" if key else "absente", ok=key)

    print()
    print("  Fichiers gérés")
    for path in sorted(all_managed_paths("server")):
        present = _state.file_present(path)
        _row(path, "présent" if present else "absent", ok=present)


def _status_agent(hostname: str, target: str) -> None:
    print()
    print("  SSH")
    reachable = _state.ssh_reachable(target)
    _row(target, "joignable" if reachable else "injoignable", ok=reachable)

    print()
    print("  K3s cluster (vue bastion)")
    token = _state.k3s_token_present()
    _row("token bastion", "présent" if token else "absent", ok=token)
    if _state.k3s_installed():
        ready, line = _state.node_ready(hostname)
        status_word = line.split()[1] if len(line.split()) > 1 else "absent"
        _row(f"node {hostname}", status_word, ok=ready)
    else:
        _row(f"node {hostname}", "k3s non installé sur bastion", ok=False)

    if reachable:
        print()
        print("  K3s agent (distant)")
        active = _state.remote_service_active(target, "k3s-agent")
        _row("service k3s-agent", _svc_label_bool(active), ok=active)

    print()
    print("  Fichiers gérés (distants)")
    for path in sorted(all_managed_paths("agent")):
        _row(path, "non vérifiable", ok=None)


def _status_backups() -> None:
    backups = _backup.list_backups()
    print()
    print("  Sauvegardes")
    if not backups:
        _row(str(_backup.BACKUP_ROOT), "aucune sauvegarde", ok=None)
        return
    total = sum(len(v) for v in backups.values())
    _row(str(_backup.BACKUP_ROOT), f"{len(backups)} fichier(s), {total} version(s)", ok=True)


def _read_bridge_name(node_dir: Path) -> str:
    dnsmasq_conf = node_dir / "dnsmasq.conf"
    if dnsmasq_conf.exists():
        for line in dnsmasq_conf.read_text().splitlines():
            if line.startswith("interface="):
                return line.split("=", 1)[1].strip()
    return "br0"


def _svc_label(name: str) -> str:
    return "active" if _state.service_active(name) else "inactive"


def _svc_label_bool(active: bool) -> str:
    return "active" if active else "inactive"


def _row(label: str, value: str, *, ok: bool | None) -> None:
    icon = {True: "✓", False: "✗", None: "?"}[ok]
    print(f"    {icon}  {label:<46} {value}")
