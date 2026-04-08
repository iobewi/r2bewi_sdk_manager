"""
role:
    Utilitaires partagés entre toutes les commandes.

responsibilities:
    - chemin racine des node dirs (NODES_DIR)
    - lecture / écriture du fichier meta.yaml d'un nœud
    - résolution de l'IP et du ssh_user depuis le meta ou la CLI
    - recherche d'un binaire dans le PATH
    - construction d'une cible SSH

does_not:
    - modifier le système
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

import yaml

NODES_DIR = Path("/etc/r2bewi/nodes")
META_FILE = "meta.yaml"


def safe_write_text(path: Path, content: str, mode: int = 0o644) -> None:
    """Écriture atomique : fichier temporaire → fsync → os.replace.

    Garantit qu'un fichier partiellement écrit (kill, disque plein) ne remplace
    jamais l'original. Le fichier temporaire est dans le même répertoire pour
    que os.replace() soit atomique (même système de fichiers).
    """
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.tmp.")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def write_meta(node_dir: Path, kind: str, ip: str | None, ssh_user: str | None) -> None:
    """Écrit le fichier meta.yaml du nœud (écriture atomique)."""
    lines = [f"kind: {kind}\n"]
    if ip:
        lines.append(f"ip: {ip}\n")
    if ssh_user:
        lines.append(f"ssh_user: {ssh_user}\n")
    safe_write_text(node_dir / META_FILE, "".join(lines), mode=0o640)


def read_meta(node_dir: Path) -> dict[str, str]:
    """Lit meta.yaml et retourne un dict. Retourne {} si absent ou invalide."""
    meta = node_dir / META_FILE
    if not meta.exists():
        return {}
    try:
        data = yaml.safe_load(meta.read_text()) or {}
    except yaml.YAMLError:
        return {}
    return {str(k): str(v) for k, v in data.items() if isinstance(k, str) and v is not None}


def resolve_ip(hostname: str, node_dir: Path, cli_ip: str | None) -> str | None:
    """
    Retourne l'IP à utiliser pour ce nœud.
    - Si cli_ip fourni → prioritaire.
    - Sinon lit meta.yaml.
    - Si kind=agent et aucune IP disponible → erreur et exit.
    """
    if cli_ip:
        return cli_ip
    meta = read_meta(node_dir)
    ip = meta.get("ip")
    if not ip and meta.get("kind") == "agent":
        from .log import error
        error(f"{hostname} est un agent mais aucune IP disponible.")
        error(f"  Fournir --ip ou relancer : sudo r2bewi init {hostname} --kind agent --ip <IP>")
        sys.exit(1)
    return ip or None


def resolve_ssh_user(node_dir: Path, cli_user: str | None, default: str = "iobewi") -> str:
    """Retourne le ssh_user : CLI explicite > meta.yaml > default.

    cli_user=None signifie « non fourni » — on consulte alors meta.yaml.
    cli_user=<valeur> (même si == default) est toujours prioritaire.
    """
    if cli_user is not None:
        return cli_user
    meta = read_meta(node_dir)
    return meta.get("ssh_user", default)


def get_kind(node_dir: Path, *, strict: bool = False) -> str:
    """Retourne le kind depuis meta.yaml.

    Si meta.yaml est absent ou ne contient pas 'kind' :
    - strict=False (défaut) : émet un avertissement puis infère via heuristique
      (netplan.yaml présent → server, sinon → agent).
    - strict=True : lève FileNotFoundError — utiliser quand une inférence silencieuse
      serait dangereuse (ex: déploiement sur un répertoire partiellement initialisé).
    """
    meta = read_meta(node_dir)
    if "kind" in meta:
        return meta["kind"]
    if strict:
        raise FileNotFoundError(
            f"kind introuvable dans {node_dir}/meta.yaml\n"
            f"  → Exécuter d'abord : sudo r2bewi init {node_dir.name} --kind <server|agent>"
        )
    from .log import warn
    warn(f"meta.yaml absent ou sans 'kind' dans {node_dir} — kind inféré par heuristique")
    return "server" if (node_dir / "netplan.yaml").exists() else "agent"


def which(cmd: str) -> bool:
    """Retourne True si cmd est trouvable et exécutable dans PATH."""
    return shutil.which(cmd) is not None


def ssh_target(hostname: str, ip: str | None, user: str = "iobewi") -> str:
    """Construit user@ip ou user@hostname.local."""
    return f"{user}@{ip}" if ip else f"{user}@{hostname}.local"
