"""
role:
    Configurer le NAT masquerade iptables pour le LAN robot.

responsibilities:
    - ajouter la règle iptables MASQUERADE si absente (idempotent)
    - sauvegarder les règles dans /etc/iptables/rules.v4
    - créer le service systemd r2bewi-nat pour réappliquer après reboot K3s

does_not:
    - installer iptables (supposé présent via le paquet)
    - gérer le réseau hôte au-delà du masquerade LAN
"""
from __future__ import annotations

from pathlib import Path

from ...system.base import info, ok, run, section, which
from ..dnsmasq.setup import read_bridge_iface, read_lan_subnet


def deploy(node_dir: Path) -> None:
    section("NAT / IP forwarding")
    _configure_nat(node_dir)


def _configure_nat(node_dir: Path) -> None:
    """
    Configure masquerade NAT pour le LAN robot.
    Idempotent : vérifie si la règle existe avant de l'ajouter.
    Un service systemd réapplique la règle après chaque redémarrage de K3s
    (K3s/Flannel réécrit les tables iptables au démarrage).
    """
    if not which("iptables"):
        info("iptables absent — NAT ignoré")
        return

    lan_subnet = read_lan_subnet(node_dir)
    bridge_iface = read_bridge_iface(node_dir)

    check = run(
        ["iptables", "-t", "nat", "-C", "POSTROUTING",
         "-s", lan_subnet, "!", "-o", bridge_iface, "-j", "MASQUERADE"],
        check=False, capture=True,
    )
    if check.returncode == 0:
        info("Règle NAT masquerade déjà présente")
    else:
        run(["iptables", "-t", "nat", "-A", "POSTROUTING",
             "-s", lan_subnet, "!", "-o", bridge_iface, "-j", "MASQUERADE"])
        info(f"Règle NAT masquerade ajoutée : {lan_subnet} → internet (via {bridge_iface})")

    rules_dir = Path("/etc/iptables")
    rules_dir.mkdir(parents=True, exist_ok=True)
    result = run(["iptables-save"], capture=True)
    (rules_dir / "rules.v4").write_text(result.stdout)
    info("Règles sauvegardées : /etc/iptables/rules.v4")

    if which("netfilter-persistent"):
        run(["netfilter-persistent", "save"], check=False)
        run(["systemctl", "enable", "netfilter-persistent"], check=False)

    _write_nat_service(lan_subnet, bridge_iface)
    ok("NAT configuré")


def _write_nat_service(lan_subnet: str, bridge_iface: str) -> None:
    unit = Path("/etc/systemd/system/r2bewi-nat.service")
    template = Path(__file__).parent / "defaults" / "server" / "r2bewi-nat.service"
    content = (
        template.read_text()
        .replace("__LAN_SUBNET__", lan_subnet)
        .replace("__BRIDGE_IFACE__", bridge_iface)
    )
    if unit.exists() and unit.read_text() == content:
        info("Service r2bewi-nat déjà à jour — ignoré")
        return
    unit.write_text(content)
    run(["systemctl", "daemon-reload"])
    run(["systemctl", "enable", "r2bewi-nat"])
    run(["systemctl", "start", "r2bewi-nat"], check=False)
    info("Service r2bewi-nat activé")
