---
paths:
  - "bootstrap/src/**/tests/**"
  - "bootstrap/src/**/test_*.py"
---
# Stratégie de tests

## Règles absolues
- Pas d'accès réseau ni root dans les tests
- Écriture uniquement dans `tmp_path` (fixture pytest)
- Mocker les chemins système : `patch.object(Path, "mkdir")`, `patch.object(Path, "write_text")`
- Prioriser les chemins d'erreur sur les chemins nominaux

## Patcher `run` correctement

```python
# run() vit dans subprocess_utils — patcher à la source, pas à l'usage
with patch("src.system.subprocess_utils.run", side_effect=fake_run):
    ...

# Pour les composants qui importent run au niveau module :
with patch("src.components.nat.setup.run", side_effect=...):
    ...
```

## Structure attendue

```
src/<zone>/tests/
  __init__.py          # vide, obligatoire
  test_<module>.py
```

## Gate CI
- Couverture minimale : **65 %** (`bootstrap/pytest.ini`)
- Objectif courant : > 85 %
- Commande locale : `make -C bootstrap test`
