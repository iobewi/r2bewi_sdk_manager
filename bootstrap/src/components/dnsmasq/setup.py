"""
role:
    Configurer dnsmasq (DNS/DHCP) et aligner systemd-resolved.

responsibilities:
    - appliquer dnsmasq.conf et r2bewi-nodes.conf
    - désactiver le stub listener de systemd-resolved
    - pointer /etc/resolv.conf vers resolved
    - exposer les helpers de lecture de config réseau (bridge, LAN)

does_not:
    - installer dnsmasq (géré par le paquet .deb)
    - gérer WireGuard ou NAT
"""
from __future__ import annotations

import os
import re
from pathlib import Path

from ...system.base import _backup, _svc, info, ok, section


def deploy(node_dir: Path) -> None:
    section("dnsmasq")
    apply(node_dir)
    apply_extra(node_dir)
    section("systemd-resolved")
    configure_resolved(node_dir)


def apply(node_dir: Path) -> None:
    """Applique dnsmasq.conf depuis le répertoire du nœud."""
    src = node_dir / "dnsmasq.conf"
    if not src.exists():
        info("dnsmasq.conf absent — ignoré")
        return
    content = src.read_text()
    dest = Path("/etc/dnsmasq.d/r2bewi.conf")
    if dest.exists() and dest.read_text() == content:
        info("dnsmasq.conf identique — ignoré")
        return
    for f in _backup.archive_directory("/etc/dnsmasq.d/", "*.conf"):
        info(f"  Archivé : {f}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(content)
    info(f"  dnsmasq.conf → {dest}")
    resolved_drop_in = Path("/etc/systemd/resolved.conf.d/r2bewi.conf")
    resolved_drop_in.parent.mkdir(parents=True, exist_ok=True)
    resolved_drop_in.write_text("[Resolve]\nDNS=127.0.0.1\nDomains=~r2bewi.internal\n")
    info(f"  resolved.conf.d/r2bewi.conf → {resolved_drop_in}")
    _svc.enable("dnsmasq")
    _svc.restart("dnsmasq")
    ok("dnsmasq appliqué")


def apply_extra(node_dir: Path) -> None:
    """Applique r2bewi-nodes.conf (entrées hosts statiques dnsmasq)."""
    src = node_dir / "r2bewi-nodes.conf"
    if not src.exists():
        return
    dest = Path("/etc/dnsmasq.d/r2bewi-nodes.conf")
    if dest.exists() and dest.read_text() == src.read_text():
        info("r2bewi-nodes.conf identique — ignoré")
        return
    dest.write_text(src.read_text())
    info(f"  r2bewi-nodes.conf → {dest}")


def add_wireguard_interface() -> None:
    """Ajoute interface=wg0 à dnsmasq pour servir r2bewi.internal aux peers VPN."""
    dnsmasq_conf = Path("/etc/dnsmasq.d/r2bewi.conf")
    if not dnsmasq_conf.exists():
        return
    content = dnsmasq_conf.read_text()
    if "interface=wg0" not in content:
        dnsmasq_conf.write_text(content.rstrip("\n") + "\ninterface=wg0\n")
        _svc.restart("dnsmasq")
        info("dnsmasq : interface=wg0 ajoutée")


def configure_resolved(node_dir: Path) -> None:
    """
    Configure systemd-resolved pour déléguer à dnsmasq :
    - désactive le stub listener (port 53 libéré pour dnsmasq)
    - pointe DNS vers 127.0.0.1
    - redirige /etc/resolv.conf vers resolved
    """
    resolved_conf = Path("/etc/systemd/resolved.conf")
    if not resolved_conf.exists():
        info("systemd-resolved absent — rien à faire")
        return
    _backup.backup_file(resolved_conf)
    domain = _read_domain(node_dir / "dnsmasq.conf")
    content = resolved_conf.read_text()
    changed = False
    if "DNSStubListener=no" not in content:
        content = re.sub(r"#?\s*DNSStubListener=.*", "DNSStubListener=no", content)
        if "DNSStubListener=no" not in content:
            content = content.rstrip("\n") + "\nDNSStubListener=no\n"
        changed = True
        info("DNSStubListener=no")
    if not re.search(r"^DNS=127\.0\.0\.1", content, re.MULTILINE):
        content = re.sub(r"#?\s*DNS=.*", "DNS=127.0.0.1", content, count=1)
        if "DNS=127.0.0.1" not in content:
            content = content.rstrip("\n") + "\nDNS=127.0.0.1\n"
        changed = True
        info("DNS=127.0.0.1")
    all_domains = re.findall(r"^[ \t]*#?[ \t]*Domains=[^\n]*$", content, re.MULTILINE)
    if all_domains != [f"Domains={domain}"]:
        content = re.sub(r"^[ \t]*#?[ \t]*Domains=[^\n]*\n?", "", content, flags=re.MULTILINE)
        content = content.rstrip("\n") + f"\nDomains={domain}\n"
        changed = True
        info(f"Domains={domain}")
    if changed:
        resolved_conf.write_text(content)
        _svc.restart("systemd-resolved")
    else:
        info("systemd-resolved déjà configuré — ignoré")
    resolv = Path("/etc/resolv.conf")
    target = "/run/systemd/resolve/resolv.conf"
    if not resolv.is_symlink() or os.readlink(str(resolv)) != target:
        resolv.unlink(missing_ok=True)
        resolv.symlink_to(target)
        info(f"/etc/resolv.conf → {target}")
    ok("systemd-resolved OK")


def restore_resolved() -> None:
    """
    Annule les changements de configure_resolved.
    Stratégie : restauration depuis backup, sinon retrait chirurgical.
    """
    resolved_conf = Path("/etc/systemd/resolved.conf")
    if not resolved_conf.exists():
        info("systemd-resolved absent — rien à restaurer")
        return
    if _backup.restore_file(str(resolved_conf)):
        from ...system.base import run
        run(["systemctl", "restart", "systemd-resolved"], check=False)
        ok("systemd-resolved restauré depuis sauvegarde")
        return
    content = resolved_conf.read_text()
    original = content
    content = re.sub(r"^DNSStubListener=no\n?", "", content, flags=re.MULTILINE)
    content = re.sub(r"^DNS=127\.0\.0\.1\n?", "", content, flags=re.MULTILINE)
    content = re.sub(r"^Domains=[^\n]*\n?", "", content, flags=re.MULTILINE)
    if content == original:
        info("systemd-resolved — aucune modification r2bewi détectée")
        return
    resolved_conf.write_text(content)
    from ...system.base import run
    run(["systemctl", "restart", "systemd-resolved"], check=False)
    ok("systemd-resolved restauré (fallback chirurgical)")


# ── Helpers de lecture de config réseau ───────────────────────────────────────

def read_bridge_iface(node_dir: Path) -> str:
    """Lit le nom de l'interface bridge depuis dnsmasq.conf."""
    dnsmasq = node_dir / "dnsmasq.conf"
    if dnsmasq.exists():
        for line in dnsmasq.read_text().splitlines():
            if line.startswith("interface="):
                return line.split("=", 1)[1].strip()
    return "br0"


def read_lan_subnet(node_dir: Path) -> str:
    """Dérive le subnet LAN depuis dnsmasq.conf (ligne dhcp-option router)."""
    dnsmasq = node_dir / "dnsmasq.conf"
    if dnsmasq.exists():
        for line in dnsmasq.read_text().splitlines():
            if line.startswith("dhcp-option=option:router,"):
                ip = line.split(",", 1)[1].strip()
                base = ".".join(ip.split(".")[:3])
                return f"{base}.0/24"
    return "192.168.82.0/24"


def read_ext_if(node_dir: Path) -> str:
    """Lit l'interface externe (non-bridge) depuis dnsmasq.conf."""
    dnsmasq = node_dir / "dnsmasq.conf"
    if dnsmasq.exists():
        for line in dnsmasq.read_text().splitlines():
            if line.startswith("interface="):
                iface = line.split("=", 1)[1].strip()
                if iface != "br0":
                    return iface
    return "eth0"


def _read_domain(dnsmasq_conf: Path) -> str:
    if not dnsmasq_conf.exists():
        return "local"
    for line in dnsmasq_conf.read_text().splitlines():
        if line.startswith("domain="):
            return line.split("=", 1)[1].strip()
    return "local"
