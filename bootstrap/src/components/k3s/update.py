"""
role:
    Réappliquer les labels K3s d'un nœud sans le ré-enrôler.

responsibilities:
    - appliquer node-role.kubernetes.io/worker=worker automatiquement
    - lire les labels r2bewi.io/* depuis node-profile.yaml
    - lire les node-label depuis k3s-config.yaml (compatibilité legacy)
    - appliquer via kubectl label --overwrite

does_not:
    - réinstaller K3s ni modifier les fichiers distants
    - redémarrer des services
"""
from __future__ import annotations

import sys

import yaml

from ...system.base import NODES_DIR, error, info, ok, run as _run_cmd, section
from ...system.profile import load_labels as _load_profile_labels
from ...core.validate import validate_node_dir


def register(sub) -> None:
    p = sub.add_parser("update", help="Mettre à jour les labels K3s du nœud")
    p.add_argument("hostname", metavar="HOSTNAME")


def run(args) -> None:
    node_dir = NODES_DIR / args.hostname
    if not node_dir.is_dir():
        error(f"Répertoire introuvable : {node_dir}")
        error(f"  Lancer d'abord : sudo r2bewi init {args.hostname} --kind agent")
        sys.exit(1)

    section("Validation")
    if not validate_node_dir(node_dir):
        error("Validation échouée — corriger les erreurs avant de mettre à jour les labels")
        sys.exit(1)
    ok("Validation OK")

    section("Mise à jour labels")
    info(f"Nœud : {args.hostname}")

    labels = ["node-role.kubernetes.io/worker=worker"]
    labels += _load_profile_labels(node_dir)

    config_file = node_dir / "k3s-config.yaml"
    if config_file.exists():
        cfg = yaml.safe_load(config_file.read_text()) or {}
        labels += [str(lbl) for lbl in cfg.get("node-label", [])]

    for label in labels:
        _run_cmd(
            ["k3s", "kubectl", "label", "node", args.hostname, label, "--overwrite"],
            check=False,
        )
        info(f"  {args.hostname} → {label}")

    ok("Labels mis à jour")

    result = _run_cmd(
        ["k3s", "kubectl", "get", "node", args.hostname, "--show-labels"],
        check=False,
        capture=True,
    )
    if result.returncode == 0:
        for line in (result.stdout or "").strip().splitlines():
            info(f"  {line}")
