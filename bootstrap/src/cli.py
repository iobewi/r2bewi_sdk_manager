"""
role:
    Point d'entrée CLI — enregistrement statique des commandes core,
    découverte dynamique des composants et dispatch.

responsibilities:
    - construire le parser en appelant register(sub) sur chaque module
    - router vers module.run(args)

does_not:
    - implémenter la logique métier
    - définir les arguments (délégué à chaque module via register)
"""
from __future__ import annotations

import argparse
import importlib
import sys

# Racine du package courant — "src" en zipapp, "bootstrap.src" en exécution source
_PKG_ROOT = __package__  # "src" ou "bootstrap.src"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="r2bewi",
        description="R2BEWI — CLI de gestion de stack robotique distribuée",
    )
    sub = parser.add_subparsers(dest="command", metavar="COMMAND")
    sub.required = True

    # Commandes core — enregistrement statique
    from .core import init, deploy, status, validate
    for mod in (init, deploy, status, validate):
        mod.register(sub)

    # Commandes composants — découverte dynamique
    from .system.component import load_all
    for comp in load_all():
        for command, module_name in comp.cli.items():
            if command not in sub._name_parser_map:
                mod = importlib.import_module(f"{_PKG_ROOT}.components.{comp.name}.{module_name}")
                mod.register(sub)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    try:
        _dispatch(args)
    except Exception as exc:
        print(f"r2bewi: {exc}", file=sys.stderr)
        sys.exit(1)


def _dispatch(args: argparse.Namespace) -> None:
    cmd = args.command
    # Core commands
    core_cmds = {"init": "init", "deploy": "deploy", "status": "status", "validate": "validate"}
    if cmd in core_cmds:
        mod = importlib.import_module(f"{_PKG_ROOT}.core.{core_cmds[cmd]}")
        mod.run(args)
        return
    # Component commands
    from .system.component import load_all
    for comp in load_all():
        if cmd in comp.cli:
            mod = comp.cli_module(cmd)
            mod.run(args)
            return
    raise ValueError(f"Commande inconnue : {cmd!r}")
