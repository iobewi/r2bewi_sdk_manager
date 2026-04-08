"""
role:
    Découverte et chargement des composants (modèle ESP-IDF).

responsibilities:
    - scanner src/*/component.yaml
    - exposer Component (applies_to, default_files, call_setup, cli_module)
    - trier par deploy_order

does_not:
    - orchestrer le déploiement (géré par node/deploy.py)
    - parser le CLI (géré par cli.py)
"""
from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from pathlib import Path

import yaml

_SRC_DIR = Path(__file__).parent.parent  # .../bootstrap/src
# Racine du package courant — "src" en zipapp, "bootstrap.src" en exécution source
_PKG_ROOT = __package__.rsplit(".", 1)[0]  # "src.system" → "src"


@dataclass
class Component:
    name: str
    description: str
    path: Path                           # src/<name>/
    kinds: list[str]                     # ["server", "agent", ...]
    deploy_order: int
    setup_fn: str | None                 # "setup.apply" → module.function
    defaults: dict[str, list[str]]       # kind → [filename, ...]
    packages: list[str]                  # system packages required (apt)
    node_files: dict[str, dict[str, str]]    # kind → {source_in_node_dir: dest_path}
    managed_paths_decl: dict[str, list[str]] # kind → [dest_path, ...]
    cli: dict[str, str]                  # command → module_name in this package

    def applies_to(self, kind: str) -> bool:
        return kind in self.kinds

    def get_node_files(self, kind: str) -> dict[str, str]:
        """Merge common + kind-specific {source: dest} for deployment."""
        result = dict(self.node_files.get("common", {}))
        result.update(self.node_files.get(kind, {}))
        return result

    def get_managed_paths(self, kind: str) -> list[str]:
        """Merge common + kind-specific destination paths."""
        paths = list(self.managed_paths_decl.get("common", []))
        paths.extend(self.managed_paths_decl.get(kind, []))
        return paths

    def default_files(self, kind: str) -> list[Path]:
        """
        Paths to default template files for the given node kind.
        Files listed under 'common' are included for every kind.
        """
        files = [
            self.path / "defaults" / "common" / name
            for name in self.defaults.get("common", [])
        ]
        files += [
            self.path / "defaults" / kind / name
            for name in self.defaults.get(kind, [])
        ]
        return files

    def call_setup(self, node_dir: Path) -> None:
        """Call the component's setup function with node_dir."""
        if not self.setup_fn:
            return
        module_name, fn_name = self.setup_fn.rsplit(".", 1)
        pkg = f"{_PKG_ROOT}.components.{self.name}.{module_name}"
        mod = importlib.import_module(pkg)
        getattr(mod, fn_name)(node_dir)

    def cli_module(self, command: str):
        """Import and return the Python module handling a CLI subcommand."""
        module_name = self.cli.get(command)
        if module_name is None:
            return None
        return importlib.import_module(f"{_PKG_ROOT}.components.{self.name}.{module_name}")


def load_all() -> list[Component]:
    """Scan src/components/*/component.yaml and return components sorted by deploy_order."""
    components: list[Component] = []
    for comp_yaml in sorted((_SRC_DIR / "components").glob("*/component.yaml")):
        data = yaml.safe_load(comp_yaml.read_text()) or {}
        comp = _parse(comp_yaml.parent, data)
        if comp is not None:
            components.append(comp)
    return sorted(components, key=lambda c: c.deploy_order)


def all_node_files(kind: str) -> dict[str, str]:
    """Aggregate {source_in_node_dir: dest_path} for all components applicable to kind."""
    result: dict[str, str] = {}
    for comp in load_all():
        if comp.applies_to(kind):
            result.update(comp.get_node_files(kind))
    return result


def all_managed_paths(kind: str) -> frozenset[str]:
    """Aggregate all system paths managed by r2bewi for the given node kind."""
    paths: set[str] = set()
    for comp in load_all():
        if comp.applies_to(kind):
            paths.update(comp.get_managed_paths(kind))
    return frozenset(paths)


def _parse(path: Path, data: dict) -> Component | None:
    name = data.get("name")
    if not name:
        return None
    return Component(
        name=name,
        description=data.get("description", ""),
        path=path,
        kinds=data.get("kind", []),
        deploy_order=int(data.get("deploy_order", 99)),
        setup_fn=data.get("setup"),
        defaults=data.get("defaults", {}),
        packages=data.get("packages", []),
        node_files=data.get("node_files", {}),
        managed_paths_decl=data.get("managed_paths", {}),
        cli=data.get("cli", {}),
    )
