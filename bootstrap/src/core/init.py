"""
role:
    Initialiser le répertoire d'un nœud dans /etc/r2bewi/nodes/<hostname>/.

responsibilities:
    - valider le hostname (RFC 952)
    - localiser les fichiers defaults (package ou dépôt local)
    - copier chaque fichier en substituant les variables
    - afficher le diff si un fichier existant a été modifié (sans --force)

does_not:
    - modifier le système ou la cible
    - déployer les fichiers (géré par node/deploy.py)
    - écraser les fichiers existants (sauf --force)
"""
from __future__ import annotations

import difflib
import ipaddress
import re
import sys
from pathlib import Path

from ..system.base import NODES_DIR, info, ok, section, warn
from ..system.helpers import write_meta, safe_write_text

_HOSTNAME_RE = re.compile(r'^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$')

_SYSTEM_DEFAULTS = Path("/usr/share/r2bewi/defaults")


def register(sub) -> None:
    p = sub.add_parser("init", help="Générer les fichiers de config dans /etc/r2bewi/nodes/<hostname>/")
    p.add_argument("hostname", metavar="HOSTNAME")
    p.add_argument("--kind", required=True, choices=("server", "agent"))
    p.add_argument("--ip", metavar="ADDRESS", default=None)
    p.add_argument("--ssh-user", metavar="USER", default=None)
    p.add_argument("--ext-if", metavar="IFACE", default="eth0",
                   help="Interface externe (WiFi/Eth) du bastion pour dnsmasq (défaut : eth0)")
    p.add_argument("--force", action="store_true", default=False,
                   help="Écraser les fichiers existants modifiés (défaut : afficher le diff)")


def run(args) -> None:
    _execute(
        hostname=args.hostname,
        kind=args.kind,
        ip=args.ip,
        ssh_user=args.ssh_user,
        ext_if=args.ext_if,
        force=args.force,
    )


def _execute(
    hostname: str,
    kind: str,
    ip: str | None = None,
    ssh_user: str | None = None,
    ext_if: str = "eth0",
    force: bool = False,
) -> None:
    if not _HOSTNAME_RE.match(hostname):
        suggestion = hostname.lower().replace("_", "-")
        print(
            f"r2bewi init: hostname invalide : {hostname!r}\n"
            "  RFC 1123 (K8s) : minuscules, chiffres et tirets uniquement.\n"
            f"  Suggestion : {suggestion!r}",
            file=sys.stderr,
        )
        sys.exit(1)

    section(f"Init {kind} : {hostname}")

    resolved_ip = ip or ("192.168.82.1" if kind == "server" else "<IP>")
    out_dir = NODES_DIR / hostname
    out_dir.mkdir(parents=True, exist_ok=True)

    has_diff = False
    for _name, src in _collect_defaults(kind):
        dest = out_dir / src.name
        content = _substitute(src.read_text(), hostname, resolved_ip, ext_if=ext_if)
        if not dest.exists():
            safe_write_text(dest, content, mode=0o640)
            info(f"  [nouveau]  {dest.name}")
        elif dest.read_text() == content:
            info(f"  [identique] {dest.name}")
        elif force:
            safe_write_text(dest, content, mode=0o640)
            info(f"  [écrasé]   {dest.name}")
        else:
            has_diff = True
            _print_diff(dest, content)

    write_meta(out_dir, kind, ip if kind == "agent" else None, ssh_user if kind == "agent" else None)
    ok(f"Fichiers dans {out_dir}")
    if has_diff:
        warn("Fichiers modifiés non écrasés — relancer avec --force pour appliquer")
    _print_next_steps(hostname, kind, ip, ssh_user)


def _collect_defaults(kind: str) -> list[tuple[str, Path]]:
    """
    Collect (filename, path) pairs for all default templates for the given kind.
    Priority: system-installed defaults first, then component directories.
    """
    # System-installed package: flat layout in /usr/share/r2bewi/defaults/<kind>/
    system_dir = _SYSTEM_DEFAULTS / kind
    if system_dir.is_dir():
        return sorted(
            (f.name, f) for f in system_dir.iterdir() if f.is_file()
        )

    # Development / local: collect from core/defaults/<kind>/ first, then components
    from ..system.component import load_all
    seen: dict[str, Path] = {}
    # Core defaults (node-profile.yaml etc.)
    core_defaults_dir = Path(__file__).parent / "defaults" / kind
    if core_defaults_dir.is_dir():
        for f in core_defaults_dir.iterdir():
            if f.is_file() and f.name not in seen:
                seen[f.name] = f
    # Component defaults
    for comp in load_all():
        if comp.applies_to(kind):
            for f in comp.default_files(kind):
                if f.exists() and f.name not in seen:
                    seen[f.name] = f
    if not seen:
        raise FileNotFoundError(
            f"Aucun fichier defaults trouvé pour kind={kind!r}\n"
            f"  Cherché dans src/core/defaults/{kind}/ et les composants src/components/*/defaults/{kind}/"
        )
    return sorted(seen.items())


def _dhcp_range(ip: str) -> tuple[str, str]:
    try:
        iface = ipaddress.IPv4Interface(f"{ip}/24")
        base = int(iface.network.network_address)
        return str(ipaddress.IPv4Address(base + 100)), str(ipaddress.IPv4Address(base + 200))
    except ValueError:
        raise ValueError(
            f"IP invalide pour le calcul DHCP : {ip!r}\n"
            "  Fournir une IPv4 valide avec --ip (ex. 192.168.82.1)"
        )


def _substitute(
    content: str,
    hostname: str,
    ip: str,
    token: str = "__TOKEN__",
    ext_if: str = "eth0",
) -> str:
    if "__DHCP_START__" in content or "__DHCP_END__" in content:
        dhcp_start, dhcp_end = _dhcp_range(ip)
    else:
        dhcp_start = dhcp_end = ""
    lan = ip.rsplit(".", 1)[0]
    return (
        content
        .replace("__HOSTNAME__", hostname)
        .replace("__IP__", ip)
        .replace("__LAN__", lan)
        .replace("__DHCP_START__", dhcp_start)
        .replace("__DHCP_END__", dhcp_end)
        .replace("__TOKEN__", token)
        .replace("__EXT_IF__", ext_if)
    )


def _print_diff(dest: Path, new_content: str) -> None:
    old_lines = dest.read_text().splitlines(keepends=True)
    new_lines = new_content.splitlines(keepends=True)
    diff = list(difflib.unified_diff(
        old_lines, new_lines,
        fromfile=f"{dest.name} (actuel)",
        tofile=f"{dest.name} (nouveau)",
        lineterm="",
    ))
    warn(f"  [diff]     {dest.name}")
    for line in diff:
        print(f"    {line}", end="" if line.endswith("\n") else "\n")


def _print_next_steps(hostname: str, kind: str, ip: str | None, ssh_user: str | None) -> None:
    deploy_cmd = f"sudo r2bewi deploy {hostname}"
    if ip:
        deploy_cmd += f" --ip {ip}"
    if ssh_user:
        deploy_cmd += f" --ssh-user {ssh_user}"
    print()
    print("Prochaine étape — éditer si besoin puis déployer :")
    print()
    print(f"  ls /etc/r2bewi/nodes/{hostname}/")
    print(f"  {deploy_cmd}")
