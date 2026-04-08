---
paths:
  - "bootstrap/src/components/**"
---
# Modèle de composant

Un composant = `bootstrap/src/components/<nom>/` avec ces fichiers :

## component.yaml

```yaml
name: <nom>
kind: [server]          # ou [agent] ou [server, agent]
deploy_order: 30        # ordre d'application (r2bewi deploy)
packages: [pkg1, pkg2]
node_files:             # fichiers poussés sur le nœud distant
  server:
    netplan.yaml: /etc/netplan/50-r2bewi.yaml
managed_paths:          # chemins gérés (status / uninstall)
  server:
    - /etc/netplan/50-r2bewi.yaml
```

## setup.py

```python
from __future__ import annotations
"""
role:
    Une phrase.
responsibilities:
    - ...
does_not:
    - ...
"""
from pathlib import Path

def deploy(node_dir: Path) -> None:
    """Idempotent obligatoire."""
    ...
```

## Checklist nouveau composant
1. `__init__.py`, `setup.py`, `component.yaml`
2. `defaults/<kind>/` pour les templates de config
3. `tests/__init__.py` + `tests/test_setup.py` (chemin heureux + chemin d'erreur)
4. Vérifier : `make show-packages` et `make -C bootstrap test` passent
