"""
role:
    Installer et configurer le serveur WireGuard sur le bastion.

responsibilities:
    - installer wireguard-tools
    - générer les clés serveur si absentes
    - écrire /etc/wireguard/wg0.conf
    - activer wg-quick@wg0
    - ajouter interface=wg0 dans dnsmasq pour le DNS VPN

does_not:
    - gérer les peers (géré par wireguard/peer.py)
    - modifier le réseau hôte au-delà de wg0
"""
from __future__ import annotations

from pathlib import Path

from ...system.base import _svc, info, ok, run, which
from ..dnsmasq.setup import add_wireguard_interface, read_ext_if


def setup(node_dir: Path) -> None:
    """
    Configure le serveur WireGuard sur le bastion.
    Idempotent : aucune action si les clés et la conf existent déjà.
    """

    wg_dir = Path("/etc/wireguard")
    wg_dir.mkdir(mode=0o700, parents=True, exist_ok=True)

    key_file = wg_dir / "wg0.key"
    pub_file = wg_dir / "wg0.pub"

    if not key_file.exists():
        result = run(["wg", "genkey"], capture=True)
        privkey = result.stdout.strip()
        key_file.write_text(privkey + "\n")
        key_file.chmod(0o600)
        result = run(["wg", "pubkey"], input=privkey, capture=True)
        pubkey = result.stdout.strip()
        pub_file.write_text(pubkey + "\n")
        pub_file.chmod(0o644)
        info(f"Clés WireGuard générées — pubkey: {pubkey[:16]}…")
    else:
        info("Clés WireGuard déjà présentes")

    conf_file = wg_dir / "wg0.conf"
    if not conf_file.exists():
        privkey = key_file.read_text().strip()
        ext_if = read_ext_if(node_dir)
        conf = (
            "[Interface]\n"
            "Address    = 10.8.0.1/24\n"
            "ListenPort = 51820\n"
            f"PrivateKey = {privkey}\n"
            f"PostUp     = iptables -t nat -A POSTROUTING -s 10.8.0.0/24 -o {ext_if} -j MASQUERADE; "
            "iptables -A FORWARD -i wg0 -j ACCEPT; iptables -A FORWARD -o wg0 -j ACCEPT\n"
            f"PostDown   = iptables -t nat -D POSTROUTING -s 10.8.0.0/24 -o {ext_if} -j MASQUERADE; "
            "iptables -D FORWARD -i wg0 -j ACCEPT; iptables -D FORWARD -o wg0 -j ACCEPT\n"
        )
        conf_file.write_text(conf)
        conf_file.chmod(0o600)
        info(f"Config WireGuard écrite : {conf_file}")
    else:
        info("Config WireGuard déjà présente — ignorée")

    _svc.enable("wg-quick@wg0")
    _svc.restart("wg-quick@wg0")
    ok("WireGuard serveur actif — port UDP 51820")

    add_wireguard_interface()
