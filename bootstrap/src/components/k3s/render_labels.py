"""
role:
    Afficher les labels qui seraient appliqués sur un nœud (dry-run).

does_not:
    - appliquer les labels
    - modifier le système
"""
from __future__ import annotations

import sys

from ...system.base import NODES_DIR, error, info, ok, section
from ...system.profile import load_labels


def register(sub) -> None:
    p = sub.add_parser("render-labels", help="Afficher les labels qui seraient appliqués sur un nœud")
    p.add_argument("hostname", metavar="HOSTNAME")


def run(args) -> None:
    node_dir = NODES_DIR / args.hostname
    if not node_dir.is_dir():
        error(f"Répertoire introuvable : {node_dir}")
        error(f"  Lancer d'abord : sudo r2bewi init {args.hostname} --kind agent")
        sys.exit(1)

    profile_path = node_dir / "node-profile.yaml"
    if not profile_path.exists():
        error(f"node-profile.yaml absent dans {node_dir}")
        error("  render-labels s'applique uniquement aux agents (--kind agent)")
        sys.exit(1)

    section(f"Labels calculés — {args.hostname}")

    auto = "node-role.kubernetes.io/worker=worker"
    info(f"  {auto}  (automatique)")

    labels = load_labels(node_dir)
    if not labels:
        error("node-profile.yaml présent mais aucun label généré — vérifier que les champs sont remplis")
        sys.exit(1)

    for label in labels:
        print(f"  {label}")

    print()
    ok(f"{len(labels) + 1} label(s) au total")
