"""
role:
    Générer un peer WireGuard (SDK, dev, robot) et sa configuration client.

responsibilities:
    - générer la paire de clés peer
    - allouer une IP dans le subnet VPN (10.8.0.0/24) sans collision
    - ajouter le [Peer] dans /etc/wireguard/wg0.conf
    - appliquer la nouvelle conf à chaud (wg set) si wg0 est actif
    - afficher ou sauvegarder la conf client

does_not:
    - modifier le réseau hôte
    - gérer les clés serveur (gérées par wireguard/server.py)
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

from ...system.base import error, info, ok, section, warn, which
from ...system.base import run as _run_cmd

_WG_DIR = Path("/etc/wireguard")
_WG_CONF = _WG_DIR / "wg0.conf"
_WG_PUB = _WG_DIR / "wg0.pub"
_SERVER_IP = "10.8.0.1"
_DEFAULT_PORT = 51820


def register(sub) -> None:
    p = sub.add_parser("wg-peer", help="Générer un peer WireGuard (SDK, dev) et sa conf client")
    p.add_argument("peer_name", metavar="PEER_NAME")
    p.add_argument("--endpoint", metavar="IP", default=None)
    p.add_argument("--port", metavar="PORT", type=int, default=51820)
    p.add_argument("--lan", metavar="SUBNET", default=None)
    p.add_argument("--out", metavar="FILE", default=None)
    p.add_argument("--dns-hook", action="store_true", default=False)


def run(args) -> None:
    if not which("wg"):
        error("wireguard-tools non installé.")
        error("  Lancer d'abord : sudo r2bewi deploy <hostname>")
        sys.exit(1)

    if not _WG_CONF.exists():
        error(f"{_WG_CONF} introuvable.")
        error("  Le serveur WireGuard n'a pas encore été déployé.")
        sys.exit(1)

    if not _WG_PUB.exists():
        error(f"{_WG_PUB} introuvable.")
        error("  Clé publique serveur manquante — réexécuter : sudo r2bewi deploy <hostname>")
        sys.exit(1)

    _execute(
        peer_name=args.peer_name,
        endpoint=args.endpoint,
        port=args.port,
        lan=args.lan,
        out=args.out,
        dns_hook=args.dns_hook,
    )


def _execute(
    peer_name: str,
    endpoint: str | None = None,
    port: int = _DEFAULT_PORT,
    lan: str | None = None,
    out: str | None = None,
    dns_hook: bool = False,
) -> None:
    section(f"WireGuard peer : {peer_name!r}")

    server_pubkey = _WG_PUB.read_text().strip()

    result = _run_cmd(["wg", "genkey"], capture=True)
    peer_privkey = result.stdout.strip()
    result = _run_cmd(["wg", "pubkey"], input=peer_privkey, capture=True)
    peer_pubkey = result.stdout.strip()
    info(f"Clés générées — pubkey: {peer_pubkey[:16]}…")

    existing_conf = _WG_CONF.read_text()
    if peer_pubkey in existing_conf:
        error(f"Ce peer existe déjà dans {_WG_CONF} (pubkey identique)")
        sys.exit(1)

    peer_ip = _next_peer_ip(existing_conf)
    info(f"IP allouée : {peer_ip}")

    peer_block = (
        f"\n# {peer_name}\n"
        f"[Peer]\n"
        f"PublicKey  = {peer_pubkey}\n"
        f"AllowedIPs = {peer_ip}/32\n"
    )
    _WG_CONF.write_text(existing_conf.rstrip("\n") + "\n" + peer_block)
    info(f"[Peer] ajouté à {_WG_CONF}")

    check = _run_cmd(["wg", "show", "wg0"], check=False, capture=True)
    if check.returncode == 0:
        _run_cmd(["wg", "set", "wg0", "peer", peer_pubkey, "allowed-ips", f"{peer_ip}/32"])
        info("Peer ajouté à chaud sur wg0 (sans redémarrage)")
    else:
        warn("wg0 non actif — peer pris en compte au prochain démarrage")

    resolved_lan = lan or _read_lan_from_wg_conf(existing_conf)
    client_conf = _build_client_conf(
        peer_name=peer_name,
        peer_privkey=peer_privkey,
        peer_ip=peer_ip,
        server_pubkey=server_pubkey,
        endpoint=endpoint,
        port=port,
        lan=resolved_lan,
        dns_hook=dns_hook,
    )

    if out:
        out_path = Path(out)
        out_path.write_text(client_conf)
        out_path.chmod(0o600)
        ok(f"Config client sauvegardée : {out_path}")
    else:
        separator = "─" * 60
        print()
        print(separator)
        print(f"# {peer_name} — WireGuard client config")
        print(separator)
        print(client_conf)
        print(separator)

    ok(f"Peer {peer_name!r} prêt — IP VPN : {peer_ip}")
    if not endpoint:
        warn("--endpoint non fourni : remplacer <BASTION_IP> dans la conf client")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _next_peer_ip(conf: str) -> str:
    used: set[int] = {1}
    for m in re.finditer(r"AllowedIPs\s*=\s*10\.8\.0\.(\d+)/32", conf):
        used.add(int(m.group(1)))
    for last_octet in range(2, 255):
        if last_octet not in used:
            return f"10.8.0.{last_octet}"
    raise RuntimeError("Subnet VPN 10.8.0.0/24 saturé — tous les peers (.2–.254) sont alloués")


def _read_lan_from_wg_conf(conf: str) -> str:
    m = re.search(r"POSTROUTING\s+-s\s+([\d./]+)", conf)
    if m and not m.group(1).startswith("10.8."):
        return m.group(1)
    return "192.168.82.0/24"


def _build_client_conf(
    peer_name: str,
    peer_privkey: str,
    peer_ip: str,
    server_pubkey: str,
    endpoint: str | None,
    port: int,
    lan: str,
    dns_hook: bool = False,
) -> str:
    endpoint_str = f"{endpoint}:{port}" if endpoint else f"<BASTION_IP>:{port}"
    allowed_ips = f"10.8.0.0/24, {lan}"

    if dns_hook:
        dns_section = (
            f"PostUp  = printf 'nameserver {_SERVER_IP}\\nsearch r2bewi.internal\\n'"
            " > /etc/resolv.conf\n"
            "PreDown = printf 'nameserver 1.1.1.1\\n' > /etc/resolv.conf\n"
        )
    else:
        dns_section = f"DNS        = {_SERVER_IP}\n"

    return (
        "[Interface]\n"
        f"# Peer : {peer_name}\n"
        f"PrivateKey = {peer_privkey}\n"
        f"Address    = {peer_ip}/32\n"
        f"{dns_section}"
        "\n"
        "[Peer]\n"
        f"PublicKey  = {server_pubkey}\n"
        f"Endpoint   = {endpoint_str}\n"
        f"AllowedIPs = {allowed_ips}\n"
        "PersistentKeepalive = 25\n"
    )
