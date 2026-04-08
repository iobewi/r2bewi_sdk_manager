"""
role:
    Générer un token temporaire Kubernetes pour Headlamp.

does_not:
    - créer le ServiceAccount ni les RBAC (portés par les manifests)
    - modifier aucun fichier système
"""
from __future__ import annotations

import sys

from ...system.base import error, info, ok, run as _run_cmd, section


def register(sub) -> None:
    p = sub.add_parser("headlamp-token", help="Générer un token temporaire pour Headlamp")
    p.add_argument("--duration",  metavar="DURATION", default="8h")
    p.add_argument("--namespace", metavar="NS",       default="ros")
    p.add_argument("--sa",        metavar="SA",       default="headlamp-ros")


def run(args) -> None:
    _execute(
        duration=args.duration,
        namespace=args.namespace,
        sa=args.sa,
    )


def _execute(
    duration: str = "8h",
    namespace: str = "ros",
    sa: str = "headlamp-ros",
) -> None:
    section("Génération token Headlamp")
    info(f"ServiceAccount : {sa}@{namespace}")
    info(f"Durée          : {duration}")

    result = _run_cmd(
        ["k3s", "kubectl", "-n", namespace, "create", "token", sa, "--duration", duration],
        check=False,
        capture=True,
    )
    if result.returncode != 0:
        error("Échec de génération du token")
        error(f"  namespace   : {namespace}")
        error(f"  account     : {sa}")
        if result.stderr:
            error(f"  kubectl     : {result.stderr.strip()}")
        error(f"  Vérifier : k3s kubectl -n {namespace} get serviceaccount {sa}")
        sys.exit(1)

    token = result.stdout.strip()
    ok(f"Token généré ({duration})")

    print()
    print("━" * 60)
    print(f"  Token Headlamp (valide {duration})")
    print("━" * 60)
    print(token)
    print("━" * 60)

    _copy_to_clipboard(token)


def _copy_to_clipboard(token: str) -> None:
    for tool, cmd_args in [
        ("xclip",   ["xclip", "-selection", "clipboard"]),
        ("xsel",    ["xsel", "--clipboard", "--input"]),
        ("wl-copy", ["wl-copy"]),
    ]:
        result = _run_cmd(["which", tool], check=False, capture=True)
        if result.returncode == 0:
            _run_cmd(cmd_args, input=token, check=False)
            ok(f"Copié dans le presse-papiers ({tool})")
            return
