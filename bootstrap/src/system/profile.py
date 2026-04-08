"""
role:
    Convertit node-profile.yaml en liste de labels K8s r2bewi.io/*.
    Valide les valeurs contre catalog/labels.yaml.

responsibilities:
    - localiser catalog/labels.yaml (package installé ou dépôt local)
    - valider le profil opérateur (validate_profile → liste d'erreurs)
    - convertir le profil en labels (load_labels → sys.exit si erreurs)

does_not:
    - appliquer les labels (géré par enroll / update)
"""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

from .log import error

_NAMESPACE = "r2bewi.io"

_SYSTEM_CATALOG = Path("/usr/share/r2bewi/catalog/labels.yaml")
_LOCAL_CATALOG = Path(__file__).parent.parent / "core" / "catalog" / "labels.yaml"


def load_catalog() -> dict:
    for candidate in (_SYSTEM_CATALOG, _LOCAL_CATALOG):
        if candidate.exists():
            return yaml.safe_load(candidate.read_text()) or {}
    raise FileNotFoundError(
        f"Catalogue introuvable.\n"
        f"  Cherché dans : {_SYSTEM_CATALOG}, {_LOCAL_CATALOG}"
    )


def validate_profile(profile: dict, catalog: dict) -> list[str]:
    """
    Valide un profil chargé contre le catalogue.
    Retourne la liste des erreurs (vide = OK).
    """
    errors: list[str] = []

    # ── compute.* ─────────────────────────────────────────────────────────────
    compute = profile.get("compute") or {}
    for key in ("accelerator", "class", "realtime"):
        val = str(compute.get(key, "")).strip()
        if not val:
            errors.append(f"'compute.{key}' est obligatoire")
        else:
            allowed = {str(v["value"]) for v in
                       catalog.get("compute", {}).get(key, {}).get("values", [])}
            if val not in allowed:
                errors.append(f"valeur invalide pour compute.{key}: {val!r} — autorisées : {sorted(allowed)}")

    # ── device.* ──────────────────────────────────────────────────────────────
    device = profile.get("device") or {}
    device_catalog = catalog.get("device", {})
    for family, val in device.items():
        if val is None or str(val).strip() == "":
            continue
        val = str(val).strip()
        if family not in device_catalog:
            errors.append(f"famille device inconnue : {family!r}")
            continue
        allowed = {str(v["value"]) for v in device_catalog[family].get("values", [])}
        if val not in allowed:
            errors.append(f"valeur invalide pour device.{family}: {val!r} — autorisées : {sorted(allowed)}")

    return errors


def profile_to_labels(profile: dict) -> list[str]:
    """Convertit un profil validé en liste de labels K8s (sans re-valider)."""
    labels: list[str] = []
    ns = _NAMESPACE

    compute = profile.get("compute") or {}
    for key in ("accelerator", "class", "realtime"):
        val = str(compute.get(key, "")).strip()
        if val:
            labels.append(f"{ns}/compute.{key}={val}")

    device = profile.get("device") or {}
    for family, val in device.items():
        if val is None:
            continue
        val = str(val).strip()
        if val:
            labels.append(f"{ns}/device.{family}={val}")

    return labels


def load_labels(node_dir: Path) -> list[str]:
    """
    Lit node-profile.yaml dans node_dir, valide contre le catalogue,
    et retourne la liste de labels K8s. Retourne [] si absent ou vide.
    sys.exit(1) si le profil contient des erreurs.
    """
    profile_path = node_dir / "node-profile.yaml"
    if not profile_path.exists():
        return []

    profile = yaml.safe_load(profile_path.read_text()) or {}
    if not profile:
        return []

    # Ne pas traiter un template non rempli (compute.accelerator est le premier champ obligatoire)
    compute = profile.get("compute") or {}
    if not str(compute.get("accelerator", "")).strip():
        return []

    try:
        catalog = load_catalog()
    except FileNotFoundError as exc:
        error(str(exc))
        sys.exit(1)

    errors = validate_profile(profile, catalog)
    if errors:
        for e in errors:
            error(f"node-profile: {e}")
        sys.exit(1)

    return profile_to_labels(profile)
