# containers — Manifests K3s

Ce module contient les manifests Kubernetes utilisés pour tester et valider le déploiement des images R2BEWI sur le cluster K3s.

## Structure

```text
containers/
├── manifests/
│   ├── ros-core-arm64-test.yaml   ← job de test ARM64
│   └── ros-headlamp-access.yaml   ← accès Headlamp
└── Makefile
```

## Déploiement sur les nœuds

Le déploiement est piloté par **K3s**. Les nœuds récupèrent leurs images depuis le registry du bastion, configuré comme miroir dans `registries.yaml` (généré par `r2bewi init`) :

```yaml
mirrors:
  "registry.r2bewi.internal:5000":
    endpoint:
      - "http://registry.r2bewi.internal:5000"
```

Les manifests référencent les images sous la forme `registry.r2bewi.internal:5000/r2bewi/<service>:<tag>`.

## Commandes

```bash
# Déployer le job de test ARM64 sur le cluster (VPN requis)
make -C containers deploy-test

# Afficher les logs du job
make -C containers logs-test

# Supprimer le job
make -C containers clean-test
```
