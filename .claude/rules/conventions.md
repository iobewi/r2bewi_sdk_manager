---
paths:
  - "bootstrap/src/**"
---
# Conventions de code — bootstrap/src

## Ne jamais faire
- `except Exception` ou `except:` — attraper uniquement `OSError`, `yaml.YAMLError`, `CommandError`
- `print()` dans le code métier — utiliser `info()`, `ok()`, `warn()`, `error()` (system/log.py)
- `Path("/etc/...").write_text()` directement — utiliser `safe_write_text()`
- F-strings non quotées dans `run_ssh()` — `ssh_quote()` sur toute valeur opérateur/réseau
- Hardcoder des chemins dans le code — déclarer `node_files` et `managed_paths` dans `component.yaml`
- `importlib.import_module("src....")` — utiliser `_PKG_ROOT` (voir cli.py)

## Toujours faire
- `from __future__ import annotations` en tête de chaque fichier source
- Docstring `role / responsibilities / does_not` en tête de module
- `safe_write_text(path, content, mode=0o640)` pour les fichiers de config critiques
- `ssh_quote(value)` autour de toute variable interpolée dans une commande SSH
- `timeout=` sur `run()` et `push_file()` pour apt-get upgrade et opérations longues

## Points d'attention

- `get_kind(node_dir, strict=False)` : sans `meta.yaml`, infère par heuristique et émet `warn()`.
  Passer `strict=True` si une inférence silencieuse est dangereuse.
- `validate_node_dir()` : appeler avant tout `deploy` ou `enroll`.
- `push_file()` : stderr SSH visible dans `CommandError.stderr` depuis le fix 2026-04-08.
- `safe_write_text()` : écriture atomique via `mkstemp → fsync → os.replace`.
- `resolve_ssh_user(node_dir, cli_user: str | None)` : `None` = non fourni, string = priorité absolue.
