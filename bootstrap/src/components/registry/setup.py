"""
role:
    Installer et configurer le registry OCI local (docker-registry).

responsibilities:
    - créer un LV LVM dédié pour le stockage (si LVM disponible)
    - installer le paquet docker-registry
    - écrire /etc/docker/registry/config.yml
    - activer et démarrer le service docker-registry

does_not:
    - gérer Docker Engine (le registry fonctionne sans Docker)
    - configurer les clients (géré par registries.yaml dans les nœuds)
"""
from __future__ import annotations

import sys
from pathlib import Path

from ...system.base import _backup, _svc, error, info, ok, run, which

_REGISTRY_CONFIG = """\
version: 0.1
log:
  fields:
    service: registry
storage:
  filesystem:
    rootdirectory: /var/lib/docker-registry
  cache:
    blobdescriptor: inmemory
http:
  addr: :5000
  headers:
    X-Content-Type-Options: [nosniff]
health:
  storagedriver:
    enabled: true
    interval: 10s
    threshold: 3
"""


def install(node_dir: Path, size: str = "256G") -> None:
    """
    Installe et configure le registry OCI sur le bastion.
    Idempotent : vérifie le montage et la présence du binaire avant toute action.
    """
    _setup_volume(size)

    config_path = Path("/etc/docker/registry/config.yml")
    config_path.parent.mkdir(parents=True, exist_ok=True)
    if not config_path.exists() or config_path.read_text() != _REGISTRY_CONFIG:
        _backup.backup_file(config_path)
        config_path.write_text(_REGISTRY_CONFIG)
        info(f"Configuration écrite : {config_path}")
    else:
        info("Configuration registry déjà à jour — ignorée")

    _svc.enable("docker-registry")
    _svc.restart("docker-registry")
    ok("Registry OCI disponible sur :5000")


def _setup_volume(size: str = "256G") -> None:
    """
    Monte un LV LVM dédié sur /var/lib/docker-registry et persiste dans fstab.
    Idempotent : aucune action si le répertoire est déjà un point de montage dédié.
    """
    mount_point = Path("/var/lib/docker-registry")
    mount_point.mkdir(parents=True, exist_ok=True)

    if _is_mounted(mount_point):
        info("Volume registry déjà monté — ignoré")
        return

    vg = _detect_vg()
    if not vg:
        info("Aucun VG LVM détecté — stockage registry sur la partition système")
        return

    lv_path = Path(f"/dev/{vg}/registry")

    if not lv_path.exists():
        if not which("lvcreate"):
            info("lvcreate absent — stockage registry sur la partition système")
            return

        requested_gb = _parse_size_gb(size)
        free_gb = _vg_free_gb(vg)
        if free_gb < requested_gb:
            error(f"Espace insuffisant dans le VG '{vg}' :")
            error(f"  Demandé : {size}  —  Disponible : {free_gb:.1f}G")
            error(f"  Réduire avec --registry-size (ex. --registry-size {int(free_gb // 1)}G)")
            sys.exit(1)

        info(f"Création du LV registry ({size}) dans {vg} ({free_gb:.1f}G libres)...")
        run(["lvcreate", "-L", size, "-n", "registry", vg])
        run(["mkfs.ext4", "-q", str(lv_path)])
        info(f"LV {lv_path} formaté en ext4")
    else:
        info(f"LV {lv_path} déjà existant")

    run(["mount", str(lv_path), str(mount_point)])
    run(["chown", "docker-registry:docker-registry", str(mount_point)])
    info(f"{lv_path} monté sur {mount_point}")

    result = run(["blkid", "-s", "UUID", "-o", "value", str(lv_path)], capture=True)
    uuid = result.stdout.strip()
    if uuid:
        fstab = Path("/etc/fstab")
        content = fstab.read_text()
        if not _fstab_has_entry(content, mount_point):
            entry = (
                f"# /var/lib/docker-registry was on /dev/{vg}/registry\n"
                f"UUID={uuid} {mount_point} ext4 defaults 0 2\n"
            )
            fstab.write_text(content + entry)
            info(f"/etc/fstab : entrée ajoutée (UUID={uuid})")
        else:
            info("/etc/fstab : entrée registry déjà présente")

    ok(f"Volume registry prêt ({mount_point})")


def _is_mounted(mount_point: Path) -> bool:
    """Retourne True si mount_point est exactement la 2e colonne d'une ligne de /proc/mounts."""
    target = str(mount_point)
    for line in Path("/proc/mounts").read_text().splitlines():
        fields = line.split()
        if len(fields) >= 2 and fields[1] == target:
            return True
    return False


def _fstab_has_entry(content: str, mount_point: Path) -> bool:
    """Retourne True si fstab contient déjà une entrée active (non commentée) pour mount_point."""
    target = str(mount_point)
    for line in content.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        fields = stripped.split()
        if len(fields) >= 2 and fields[1] == target:
            return True
    return False


def _detect_vg() -> str | None:
    result = run(["vgs", "--noheadings", "-o", "vg_name"], check=False, capture=True)
    if result.returncode != 0:
        return None
    lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    return lines[0] if lines else None


def _parse_size_gb(size: str) -> float:
    """Convertit '256G' ou '1T' en float (Go). Lève ValueError si format invalide."""
    s = size.strip().upper()
    if s.endswith("T"):
        return float(s[:-1]) * 1024
    if s.endswith("G"):
        return float(s[:-1])
    raise ValueError(f"Format de taille invalide : {size!r} (attendu : ex. 256G, 1T)")


def _vg_free_gb(vg: str) -> float:
    result = run(
        ["vgs", "--noheadings", "--units", "g", "--nosuffix", "-o", "vg_free", vg],
        check=False, capture=True,
    )
    if result.returncode != 0:
        return 0.0
    try:
        return float(result.stdout.strip())
    except ValueError:
        return 0.0
