# R2BEWI SDK

SDK de gestion de stack robotique distribuée K3s (Raspberry Pi / Jetson).

## Répertoires

| Répertoire | Rôle |
|---|---|
| `bootstrap/` | CLI Python `r2bewi` — init, deploy, enroll, validate, status |
| `containers/` | Images Docker des services (registry privé, bastion) |
| `docs/` | runbook, labels K3s, whitebook, contributing |
| `.github/workflows/ci.yml` | CI : lint + tests + smoke (Python 3.10 / 3.12) |

## Commandes

```bash
make bootstrap-test           # lint + tests + couverture (depuis la racine)
make -C bootstrap test-dev    # idem + pip install auto
make -C bootstrap lint        # py_compile uniquement
make -C bootstrap build       # → bootstrap/dist/r2bewi
make -C bootstrap show-packages
```

## Architecture bootstrap/src

```
cli.py                        # point d'entrée, build_parser(), _dispatch()
core/                         # init, deploy, validate, status
components/<nom>/             # composants système (voir .claude/rules/components.md)
system/
  helpers.py                  # read_meta, write_meta, get_kind, safe_write_text
  subprocess_utils.py         # run(), run_ssh(), push_file(), CommandError, ssh_quote
  component.py                # chargement component.yaml, all_node_files()
  log.py                      # info(), ok(), warn(), error(), section()
  base.py                     # ré-exporte les symboles clés
  state.py                    # lectures read-only (service_active, node_ready…)
  debian/packages.py          # install_packages(), agent_packages()
  debian/services.py          # enable/start/restart/stop/disable/is_active
```

### Package root dynamique

`_PKG_ROOT = __package__` dans `cli.py` → `"src"` en zipapp, `"bootstrap.src"` depuis les sources.
Utiliser cette variable dans tous les `importlib.import_module` — ne jamais hardcoder `"src."`.

## Références

@./docs/contributing.md
- `docs/runbook.md` — procédure d'installation bastion + nœuds
- `docs/labels.md` — convention labels K3s `r2bewi.io/`
- `docs/whitebook.md` — vision architecture
