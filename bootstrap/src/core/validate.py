"""
role:
    Valider les fichiers de configuration d'un nœud.

responsibilities:
    - enregistrer les validateurs pour chaque fichier de config connu
    - valider les fichiers présents dans /etc/r2bewi/nodes/<hostname>/
    - exposer validate_node_dir() pour les autres modules (deploy, enroll, update)

does_not:
    - modifier le système ou les fichiers
    - appliquer la configuration
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Callable

import yaml

from ..system.base import NODES_DIR, error, info, ok, section
from ..system.helpers import get_kind
from ..system.profile import load_catalog, validate_profile


def register(sub) -> None:
    p = sub.add_parser("validate", help="Valider les fichiers de config d'un nœud")
    p.add_argument("hostname", metavar="HOSTNAME")
    p.add_argument("--file", metavar="FILE", nargs="+", dest="files",
                   help="Valider uniquement ces fichiers (défaut : tous)")


# Fichiers obligatoires par kind — leur absence bloque deploy et enroll
_REQUIRED_FILES: dict[str, list[str]] = {
    "server": ["netplan.yaml", "sysctl.conf", "dnsmasq.conf", "k3s-config.yaml", "registries.yaml"],
    "agent":  ["k3s-config.yaml", "registries.yaml", "node-profile.yaml"],
}

# ── Registre des validateurs ──────────────────────────────────────────────────

_REGISTRY: dict[str, Callable[[Path], list[str]]] = {}


def _register(filename: str) -> Callable:
    def decorator(fn: Callable[[Path], list[str]]) -> Callable[[Path], list[str]]:
        _REGISTRY[filename] = fn
        return fn
    return decorator


# ── Validateurs ───────────────────────────────────────────────────────────────

@_register("node-profile.yaml")
def _validate_node_profile(path: Path) -> list[str]:
    try:
        profile = yaml.safe_load(path.read_text()) or {}
    except yaml.YAMLError as exc:
        return [f"YAML invalide : {exc}"]
    if not profile:
        return ["fichier vide"]
    try:
        catalog = load_catalog()
    except FileNotFoundError as exc:
        return [str(exc)]
    return validate_profile(profile, catalog)


@_register("k3s-config.yaml")
def _validate_k3s_config(path: Path) -> list[str]:
    try:
        cfg = yaml.safe_load(path.read_text()) or {}
    except yaml.YAMLError as exc:
        return [f"YAML invalide : {exc}"]
    errors: list[str] = []
    kind = get_kind(path.parent)
    if kind == "agent":
        server = str(cfg.get("server", "")).strip()
        if not server:
            errors.append("'server' est obligatoire")
        elif not server.startswith("https://"):
            errors.append(f"'server' doit commencer par https:// — valeur : {server!r}")
        token = str(cfg.get("token", "")).strip()
        if not token:
            errors.append("'token' est obligatoire")
    node_labels = cfg.get("node-label", [])
    if not isinstance(node_labels, list):
        errors.append("'node-label' doit être une liste")
    else:
        for i, lbl in enumerate(node_labels):
            if not isinstance(lbl, str) or "=" not in lbl:
                errors.append(f"'node-label[{i}]' invalide : {lbl!r} (format attendu : clé=valeur)")
    return errors


@_register("netplan.yaml")
def _validate_netplan(path: Path) -> list[str]:
    try:
        cfg = yaml.safe_load(path.read_text()) or {}
    except yaml.YAMLError as exc:
        return [f"YAML invalide : {exc}"]
    errors: list[str] = []
    if "network" not in cfg:
        errors.append("clé 'network' manquante")
        return errors
    network = cfg["network"]
    if not isinstance(network, dict):
        errors.append("'network' doit être un dictionnaire")
        return errors
    if "version" not in network:
        errors.append("'network.version' manquant (valeur attendue : 2)")
    elif network["version"] != 2:
        errors.append(f"'network.version' doit être 2 — valeur : {network['version']!r}")
    if not any(k in network for k in ("ethernets", "wifis", "bridges", "bonds", "vlans")):
        errors.append("aucune interface déclarée dans 'network' (ethernets, wifis, bridges…)")
    return errors


@_register("sysctl.conf")
def _validate_sysctl(path: Path) -> list[str]:
    errors: list[str] = []
    try:
        lines = path.read_text().splitlines()
    except OSError as exc:
        return [f"Lecture impossible : {exc}"]
    for i, line in enumerate(lines, start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "=" not in stripped:
            errors.append(f"ligne {i} : format invalide (attendu clé=valeur) — {stripped!r}")
    return errors


# ── Interface publique ────────────────────────────────────────────────────────

def _validate_one(filename: str, path: Path) -> bool:
    """Valide un fichier unique via son validateur enregistré. Retourne True si OK."""
    errs = _REGISTRY[filename](path)
    if errs:
        error(f"  {filename}")
        for e in errs:
            error(f"    {e}")
        return False
    info(f"  ✓ {filename}")
    return True


def validate_node_dir(node_dir: Path, kind: str | None = None) -> bool:
    """Valide les fichiers de config du node dir.

    Si kind est fourni, vérifie d'abord la présence des fichiers obligatoires.
    Retourne False si un fichier requis est absent ou si la validation de contenu échoue.
    """
    if kind is None:
        try:
            kind = get_kind(node_dir)
        except OSError as exc:
            error(f"Impossible de détecter le kind ({node_dir}) : {exc}")
            kind = None

    # Vérification des fichiers obligatoires
    if kind in _REQUIRED_FILES:
        missing = [f for f in _REQUIRED_FILES[kind] if not (node_dir / f).exists()]
        if missing:
            for f in missing:
                error(f"Fichier requis manquant : {f}")
                error(f"  → Lancer d'abord : sudo r2bewi init {node_dir.name} --kind {kind}")
            return False

    # Validation de contenu (existante)
    targets = {
        filename: node_dir / filename
        for filename in _REGISTRY
        if (node_dir / filename).exists()
    }
    if not targets:
        error(f"Aucun fichier connu à valider dans {node_dir}")
        error(f"  → Lancer d'abord : sudo r2bewi init {node_dir.name} --kind <server|agent>")
        return False

    ok_count = 0
    fail_count = 0
    for filename, path in sorted(targets.items()):
        success = _validate_one(filename, path)
        if success:
            ok_count += 1
        else:
            fail_count += 1

    if fail_count:
        error(f"{fail_count} erreur(s) détectée(s) — corriger avant deploy / enroll")
        return False

    return True


def run(args) -> None:
    node_dir = NODES_DIR / args.hostname
    if not node_dir.is_dir():
        error(f"Répertoire introuvable : {node_dir}")
        error(f"  Lancer d'abord : sudo r2bewi init {args.hostname} --kind <server|agent>")
        sys.exit(1)

    # Vérification des fichiers requis (même règle que l'API validate_node_dir)
    try:
        kind = get_kind(node_dir)
    except OSError:
        kind = None
    if kind in _REQUIRED_FILES:
        missing = [f for f in _REQUIRED_FILES[kind] if not (node_dir / f).exists()]
        if missing:
            for f in missing:
                error(f"Fichier requis manquant : {f}")
                error(f"  → Lancer d'abord : sudo r2bewi init {args.hostname} --kind {kind}")
            sys.exit(1)

    targets = _resolve_targets(node_dir, args.files)
    if not targets:
        error(f"Aucun fichier connu à valider dans {node_dir}")
        sys.exit(1)

    section(f"Validation — {args.hostname}")
    total_errors = 0
    for filename, path in sorted(targets.items()):
        errs = _REGISTRY[filename](path)
        if errs:
            total_errors += len(errs)
            print(f"  ✗  {filename}")
            for e in errs:
                print(f"       {e}")
        else:
            print(f"  ✓  {filename}")

    print()
    if total_errors:
        error(f"{total_errors} erreur(s) détectée(s) — corriger avant deploy / enroll")
        sys.exit(1)
    else:
        ok("Tous les fichiers sont valides")


def _resolve_targets(node_dir: Path, files: list[str] | None) -> dict[str, Path]:
    if files:
        result = {}
        for f in files:
            if f not in _REGISTRY:
                error(f"Aucun validateur pour : {f!r}")
                error(f"  Fichiers supportés : {sorted(_REGISTRY)}")
                sys.exit(1)
            path = node_dir / f
            if not path.exists():
                error(f"Fichier introuvable : {path}")
                sys.exit(1)
            result[f] = path
        return result
    return {
        filename: node_dir / filename
        for filename in _REGISTRY
        if (node_dir / filename).exists()
    }
