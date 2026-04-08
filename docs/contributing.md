# Guide contributeur — R2BEWI SDK

Ce document couvre les conventions de code, la stratégie de tests et la configuration
de l'environnement de développement local.

---

## 1. Environnement de développement

### Prérequis

- Python 3.10 ou 3.12 (les deux versions sont testées en CI)
- `make`, `bash`

### Installation

```bash
# Dépendances de test et de couverture
pip install -r bootstrap/requirements-dev.txt

# Vérification rapide
make -C bootstrap lint
make -C bootstrap test
```

---

## 2. Standards de code

### Conventions générales

- **Python 3.10+ uniquement** — annotations `X | Y`, `match/case` autorisés.
- `from __future__ import annotations` en tête de chaque fichier source.
- Noms de variables et commentaires **en français** (domaine métier), noms de
  symboles Python **en anglais** (fonctions, classes, variables).
- Pas de `print` brut dans le code métier — utiliser les helpers de `system/log.py` :
  `info()`, `ok()`, `warn()`, `error()`, `section()`.
- Imports `from __future__` puis stdlib, puis internes — pas d'imports en étoile.

### Modules et responsabilités

Chaque fichier source doit ouvrir par une docstring décrivant :

```python
"""
role:
    Une phrase — ce que fait ce module.

responsibilities:
    - bullet list des responsabilités concrètes

does_not:
    - ce qui est explicitement hors scope

side_effects:  # si applicable
    - modifications du système de fichiers, appels réseau, etc.
"""
```

### Écriture de fichiers système

Toujours utiliser `safe_write_text()` (définie dans `system/helpers.py`) pour les
fichiers de configuration :

```python
from ..system.helpers import safe_write_text
safe_write_text(Path("/etc/r2bewi/nodes/r2arm01/meta.yaml"), content, mode=0o640)
```

`safe_write_text` garantit une écriture atomique (`mkstemp` → `fsync` → `os.replace`)
et nettoie le temporaire en cas d'erreur.

### Commandes SSH

Toute valeur externe interpolée dans une commande distante doit être quotée :

```python
from ..system.subprocess_utils import ssh_quote
run_ssh(target, f"sudo hostnamectl set-hostname {ssh_quote(hostname)}")
```

`ssh_quote` est un alias de `shlex.quote` — ne jamais insérer de f-string brute
avec une valeur provenant de l'opérateur ou du réseau.

### Gestion des exceptions

- Attraper uniquement les exceptions attendues (`OSError`, `yaml.YAMLError`, etc.).
- Ne jamais utiliser `except Exception` ni `except:` — les bugs doivent remonter.
- Logger l'erreur avant de retourner un état dégradé :

```python
try:
    kind = get_kind(node_dir)
except OSError as exc:
    error(f"Impossible de détecter le kind ({node_dir}) : {exc}")
    kind = None
```

---

## 3. Stratégie de tests

### Principes

| Règle | Raison |
|---|---|
| Pas d'accès réseau réel | Les tests doivent passer hors ligne et sans root |
| Pas d'écriture hors `tmp_path` | Utiliser `tmp_path` (fixture pytest) pour tout fichier temporaire |
| Mocker les chemins système | `/etc/`, `/var/`, `/proc/` → `patch.object(Path, "read_text")` ou `patch.object(Path, "mkdir")` |
| Un test = une assertion | Préférer plusieurs petits tests ciblés à un test monolithique |

### Organisation

```
src/
  components/<comp>/tests/   ← tests spécifiques au composant
  core/tests/                ← tests des commandes CLI core
  system/tests/              ← tests des utilitaires système
```

Chaque répertoire `tests/` doit contenir un `__init__.py` vide.

### Couverture

La gate CI est à **65 %** (configurée dans `pytest.ini`). L'objectif courant est
\> 85 %. Pour consulter les lignes non couvertes :

```bash
python3 -m pytest --cov=src --cov-report=term-missing
```

Prioriser les chemins d'erreur sur les chemins nominaux : un test qui vérifie qu'une
`CommandError` est bien levée sur timeout apporte plus de valeur qu'un test qui
réplique le chemin heureux déjà couvert.

### Écriture d'un test

```python
class TestMyFeature:
    def test_error_path(self, tmp_path):
        """Description courte du cas testé."""
        from src.system.helpers import my_function
        with patch("src.system.helpers.run", side_effect=CommandError(...)):
            with pytest.raises(SystemExit) as exc:
                my_function(tmp_path)
        assert exc.value.code == 1
```

---

## 4. Hooks pré-commit

Installer les hooks localement pour attraper les erreurs avant chaque commit :

```bash
pip install pre-commit
pre-commit install
```

Le fichier `.pre-commit-config.yaml` à la racine du dépôt configure :

| Hook | Ce qu'il vérifie |
|---|---|
| `check-yaml` | YAML valide (component.yaml, ci.yml…) |
| `end-of-file-fixer` | Fichiers terminés par un saut de ligne |
| `trailing-whitespace` | Espaces en fin de ligne |
| `python-lint` | `python3 -m py_compile` sur tous les `.py` |
| `pytest-fast` | `pytest -q --no-cov -x` sur les tests rapides |

> Le hook `pytest-fast` n'exécute pas la couverture — il vérifie seulement qu'aucun
> test ne régresse. La gate de couverture complète est réservée à la CI.

---

## 5. Cycle CI

```
push / PR → main
  ├── job test (Python 3.10 + 3.12)
  │   ├── lint     : py_compile sur tous les .py
  │   ├── tests    : pytest + couverture ≥ 65 %
  │   └── artifact : .coverage (Python 3.12 uniquement)
  └── job smoke (après test)
      ├── build    : make -C bootstrap build
      └── smoke    : r2bewi --help + grep "r2bewi"
```

Un PR ne peut être mergé que si les deux jobs sont verts.

---

## 6. Ajouter un composant

1. Créer `src/components/<nom>/` avec `__init__.py`, `setup.py`, `component.yaml`.
2. Déclarer dans `component.yaml` : `name`, `kind`, `deploy_order`, `packages`,
   `node_files`, `managed_paths` (voir composants existants comme référence).
3. Implémenter `setup.deploy(node_dir)` — idempotent obligatoire.
4. Ajouter `src/components/<nom>/tests/` avec au minimum :
   - un test du chemin heureux (mocké),
   - un test du chemin d'erreur principal.
5. Vérifier que `make show-packages` et `make -C bootstrap test` passent.

---

## 7. Références rapides

```bash
make -C bootstrap lint          # vérification syntaxe Python
make -C bootstrap test          # tests + couverture (gate 65 %)
make -C bootstrap test-dev      # idem + pip install deps auto
make -C bootstrap build         # binaire dist/r2bewi
make -C bootstrap show-packages # paquets par composant
make -C bootstrap clean         # nettoyage dist/
```
