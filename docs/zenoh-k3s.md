# Zenoh + K3s — Architecture middleware ROS2

Ce document décrit la topologie du middleware de communication ROS2 dans R2BEWI SDK MANAGER.
R2BEWI utilise `rmw_zenoh_cpp` comme couche de transport ROS2 à la place de DDS.

---

## 1. Pourquoi Zenoh

`rmw_zenoh_cpp` remplace les implémentations DDS (CycloneDDS, FastDDS) par Zenoh :

| Critère | DDS | Zenoh |
|---|---|---|
| Découverte | Multicast (fragile sur LAN robot) | Gossip via routeur |
| Routage cross-host | Bridges DDS complexes | Natif |
| Config réseau | Fastidieuse (TTL, multicast) | DNS K8s |
| Footprint | Lourd | Léger |

---

## 2. Rôle du routeur Zenoh

Le routeur (`rmw_zenohd`) est **obligatoire** avec `rmw_zenoh_cpp` — la découverte multicast est désactivée par défaut.

```
ROS Node → session Zenoh → routeur Zenoh → réseau
```

Responsabilités du routeur :
- **Découverte** des nœuds ROS2 (gossip)
- **Routage** des données entre sessions

---

## 3. Topologie R2BEWI

### Nœuds du cluster

| Nœud | Architecture | Rôle ROS2 | Rôle Zenoh |
|---|---|---|---|
| Bastion x86 | x86 | Services centraux | Routeur + infra |
| Nœud motion | ARM (RPi) | Commande moteur / I/O | Routeur + client |
| Nœud perception | ARM + GPU (Jetson) | Vision + inférence | Routeur + client |

### Schéma

```
┌─────────────────────────────────────────────────────────┐
│  K3s cluster                                            │
│                                                         │
│  ┌──────────────┐   ┌──────────────┐  ┌─────────────┐  │
│  │   Bastion    │   │    Motion    │  │ Perception  │  │
│  │              │   │              │  │             │  │
│  │ rmw_zenohd ◄─┼───► rmw_zenohd ◄┼──► rmw_zenohd │  │
│  │              │   │              │  │             │  │
│  │  ROS nodes   │   │  ROS nodes   │  │  ROS nodes  │  │
│  └──────────────┘   └──────────────┘  └─────────────┘  │
│         ▲                  ▲                  ▲         │
│         └──────────────────┴──────────────────┘         │
│              zenoh-router-headless:7447                 │
└─────────────────────────────────────────────────────────┘
```

---

## 4. Déploiement K3s

### DaemonSet — 1 routeur par host

Le routeur tourne en `DaemonSet` : exactement 1 pod par nœud K3s, quelle que soit l'évolution du cluster.

```yaml
apiVersion: apps/v1
kind: DaemonSet
metadata:
  name: zenoh-router
  namespace: r2bewi
spec:
  selector:
    matchLabels:
      app: zenoh-router
  template:
    metadata:
      labels:
        app: zenoh-router
    spec:
      containers:
        - name: zenoh-router
          image: registry.r2bewi.internal:5000/r2bewi/core:latest
          command:
            - /bin/bash
            - -c
            - source /opt/ros/jazzy/setup.bash && ros2 run rmw_zenoh_cpp rmw_zenohd
          volumeMounts:
            - name: zenoh-config
              mountPath: /zenoh
          env:
            - name: ZENOH_CONFIG
              value: /zenoh/config.json5
      volumes:
        - name: zenoh-config
          configMap:
            name: zenoh-router-config
```

### Headless Service — mesh entre routeurs

Un `Headless Service` (`clusterIP: None`) expose tous les pods du DaemonSet par leur IP directe.
Les routeurs s'interconnectent automatiquement via la résolution DNS.

```yaml
apiVersion: v1
kind: Service
metadata:
  name: zenoh-router-headless
  namespace: r2bewi
spec:
  clusterIP: None
  selector:
    app: zenoh-router
  ports:
    - name: zenoh
      port: 7447
      protocol: TCP
```

### ConfigMap — configuration Zenoh

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: zenoh-router-config
  namespace: r2bewi
data:
  config.json5: |
    {
      listen: {
        endpoints: ["tcp/0.0.0.0:7447"]
      },
      connect: {
        endpoints: ["tcp/zenoh-router-headless.r2bewi.svc.cluster.local:7447"]
      }
    }
```

**Règle :** `listen` utilise une adresse locale (`0.0.0.0`), `connect` utilise le DNS K8s.

---

## 5. Comportement du mesh

Lors du démarrage d'un routeur :

1. Résolution DNS → `zenoh-router-headless` retourne la liste des IPs des pods
2. Tentatives de connexion vers chaque IP (y compris lui-même)
3. Zenoh ignore la connexion à soi-même — pas de boucle, pas d'erreur

Le mesh est **automatique** : tout nouveau nœud K3s reçoit un pod routeur (DaemonSet) qui s'intègre sans configuration manuelle.

---

## 6. Configuration des nœuds ROS2

Chaque nœud ROS2 se connecte au routeur local de son host :

```json5
{
  mode: "client",
  connect: {
    endpoints: ["tcp/zenoh-router-headless.r2bewi.svc.cluster.local:7447"]
  }
}
```

Variable d'environnement à définir dans chaque pod ROS2 :

```yaml
env:
  - name: RMW_IMPLEMENTATION
    value: rmw_zenoh_cpp
  - name: ZENOH_CONFIG
    value: /zenoh/config.json5
```

---

## 7. Pièges à éviter

| Piège | Raison |
|---|---|
| IP de pod hardcodées | Les IPs changent à chaque restart |
| `clusterIP` non-None pour le mesh | Le load balancing casse le local-first |
| DNS dans `listen` | `listen` doit être une adresse locale |
| Plusieurs routeurs par host | Conflits de port 7447 |
| Full mesh complexe dès le départ | Commencer par le pattern simple (1 routeur bastion) |

---

## 8. Progression recommandée

### Étape 1 — Pattern simple (démarrage)

1 routeur sur le bastion, tous les nœuds s'y connectent.

```
ROS nodes → bastion:7447
```

### Étape 2 — Pattern distribué (cible R2BEWI)

DaemonSet + Headless Service, routeur local sur chaque host.

```
ROS nodes → routeur local → mesh Zenoh
```

---

## Références

- [rmw_zenoh_cpp — ROS2 Jazzy](https://docs.ros.org/en/jazzy/Installation/RMW-Implementations/Non-DDS-Implementations/Working-with-Zenoh.html)
- [`docs/labels.md`](labels.md) — labels K3s `r2bewi.io/`
- [`containers/manifests/`](../containers/manifests/) — manifests K3s du projet
